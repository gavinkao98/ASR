# Architecture

This document covers the design decisions that aren't obvious from reading the code — mostly the places where Windows, antivirus software, or hardware forced a particular structure.

## Overview

```
CapsLock hold ──► Recorder ──► VAD trim ──► ASR engine ──► post-process chain ──► inject at cursor
                 (sounddevice)  (silero)   (Qwen3/Breeze)  (punct→tradify→        (clipboard helper
                                                            digits→hotwords→       subprocess)
                                                            repeat-guard)
```

| Module | Responsibility |
|---|---|
| `app/hotkey.py`, `app/ptt_logic.py` | Global key hook, and the tap-vs-hold decision |
| `app/audio/recorder.py`, `app/audio/vad.py` | Microphone capture; trimming silence |
| `app/engines/` | ASR engine adapters behind a shared interface |
| `app/postprocess/` | Text cleanup chain |
| `app/inject.py`, `app/clipboard_helper.py`, `app/clipwin.py` | Getting text into the focused window |
| `app/pipeline.py` | The coordinator wiring all of the above together |
| `app/ui/` | Tray icon, recording overlay, settings window (pywebview) |

## Threading model

Three threads matter, and the split exists for one reason: **a global keyboard hook must never block.**

1. **Hook thread** — owned by the `keyboard` library. Its callbacks do nothing but flip state and enqueue. If this thread stalls, the user's entire keyboard stalls with it.
2. **Pipeline worker** — a single daemon thread draining a `queue.Queue` (`app/pipeline.py`). Recognition takes hundreds of milliseconds to seconds, so it happens here. Single-threaded by design: two concurrent transcriptions would race to paste into the same cursor.
3. **Main thread** — owned by pywebview, which requires it for the WinForms message loop. The tray icon (`pystray.run_forever()`) also wants to block forever, so the tray is pushed onto a background thread and pywebview keeps the main one.

## Push-to-talk: tap vs. hold

The hotkey defaults to `CapsLock`, a key that already has a job. `PttStateMachine` (`app/ptt_logic.py`) separates the two uses by duration: a press shorter than the threshold is a *tap* (pass it through, let Windows toggle capitals), longer is a *hold* (record).

The state machine takes timestamps as arguments rather than calling a clock, and has no OS imports at all. That's what makes push-to-talk behaviour — including auto-repeat suppression, which is the subtle part — testable without a keyboard.

One consequence worth knowing: recording starts on key-down, *before* we know whether this is a tap or a hold. It has to, or a hold would lose its first syllable. The cancel path (`Pipeline.on_record_cancel`) discards the audio when the press turns out to be a tap. The start sound and overlay fire only once the hold threshold is crossed, so a normal CapsLock tap stays silent and invisible.

## Text injection, and why the clipboard is involved

Windows has no reliable API for "insert this text into whatever has focus." Synthesising per-character key events breaks on IMEs, non-BMP characters, and anything with input validation. So injection sets the clipboard and sends `Ctrl+V`.

That borrows a system-wide resource the user is also using, so the previous clipboard contents are captured first and restored afterwards — and not just text. Images, file lists, and rich text (Word/HTML) round-trip byte-identical, because restoration copies *every* advertised clipboard format rather than just the one we understand.

Two limits are inherent rather than bugs:

- **Elevated windows reject injection** from a non-elevated process. That's a Windows security boundary doing its job. The text is still on the clipboard, so manual `Ctrl+V` works.
- **Advanced paste state can't survive.** Excel's marching-ants marquee after a copy is cleared by *any* clipboard write, not specifically by ours.

## Clipboard isolation: the helper process

Clipboard I/O does not run in the main process. `app/clipboard_helper.py` is a long-lived child process that owns all clipboard access, speaking a small multi-turn protocol over stdio.

The reason is defensive. The Win32 clipboard is a global lock that any process can hold, and antivirus products, clipboard managers, and RDP clients all hook it aggressively. In-process clipboard calls under that contention were a source of hard crashes — heap corruption, not catchable exceptions, which take the whole application down with them.

Moving clipboard access into a child process converts "the app dies" into "the helper dies and respawns." The main process and the paste result are unaffected.

`app/clipwin.py` holds the raw `ctypes` clipboard primitives and is deliberately **dependency-free**, so the helper can start without importing the application's dependency tree. The helper is warmed at boot (`warm_clipboard_helper()`) because its cold start is ~0.8s, most of it antivirus scanning the new process — better paid once at startup than on the user's first sentence.

## Engines

`app/engines/base.py` defines the interface; `EngineManager` handles switching and holds a lock so a transcription in flight can't be unloaded from under it.

Engines declare their own capabilities, and the post-processing chain reads those declarations:

| Engine | `has_punct` | `outputs_simplified` | Runtime |
|---|---|---|---|
| Qwen3-ASR-1.7B | yes | yes | `llama-server` subprocess over localhost |
| Breeze-ASR-25 (deprecated) | no | no | CTranslate2 in-process |

Both require an NVIDIA GPU: the bundled `llama-server` is a CUDA build, and `BreezeEngine.load()` asks for `device="cuda"` outright. There is no CPU fallback, so `Bridge.download_engine()` refuses to download anything when `app.gpu.detect()` finds no CUDA device — failing before a multi-gigabyte download rather than after it.

Breeze is scheduled for removal in v1.2. Its dependencies live in `requirements-breeze.txt` and are not installed by default; everything the default path needs is in `requirements.lock.txt`.

This is why the chain is built per-engine rather than fixed: punctuation restoration is skipped when the engine already punctuates, and Simplified→Traditional conversion is skipped when the engine already emits Traditional.

### CUDA DLL loading

This exists **only for Breeze**. Qwen3 talks to `llama-server`, a separate process that ships its own CUDA runtime, so the default install needs none of it.

`main._inject_nvidia_dlls()` runs at **module scope, before any other import**, and `tests/conftest.py` imports `main` for exactly that reason. Both `os.add_dll_directory()` and a `PATH` prepend are needed: CTranslate2's own DLLs are found by the former, but cuDNN 8 loads its submodules by bare filename through the standard search order, which ignores `add_dll_directory`. Only doing one of the two produces a load failure that looks like a missing-CUDA error.

The function returns silently when the `nvidia` packages aren't installed — which is now the normal case, since they moved to `requirements-breeze.txt`. That is also what lets the test suite run GPU-free in CI. When Breeze goes away in v1.2, this function goes with it, and so does the `setuptools<81` pin that CTranslate2 forces.

### GPU detection

`app/gpu.py` asks the CUDA driver (`nvcuda.dll`) directly through `ctypes`. It deliberately does **not** use `ctranslate2.get_cuda_device_count()`, which is what it replaced: ctranslate2 is a Breeze dependency, and a hardware check for the *default* engine must not depend on an optional component. Loading `nvcuda.dll` succeeds exactly when the NVIDIA driver is installed, which is the same condition that decides whether the CUDA `llama-server` can start — so it answers the question actually being asked.

## Post-processing chain

`app/postprocess/chain.py` composes single-purpose transforms, each independently testable:

| Stage | Purpose |
|---|---|
| `punct` | Restore punctuation (skipped when the engine punctuates natively) |
| `tradify` | Simplified → Traditional, with Taiwan-specific vocabulary (OpenCC) |
| `normalize` | Whitespace and full/half-width cleanup |
| `digits` | Chinese numerals → Arabic (「四零九六」→ 4096, 「十二GB」→ 12GB) |
| `hotwords` | User-defined `misheard=correct` substitutions |
| `repeat_guard` | Suppress the degenerate repeated-token output ASR models emit on silence or noise |

Most user-visible complaints about recognition quality get fixed here rather than in the engine, which is why this layer has the densest test coverage in the project.

## Testing strategy

The Windows API surface is pushed to the edges so the interesting logic stays testable. `PttStateMachine` takes injected timestamps; the post-processing stages are pure functions; `Pipeline` takes every collaborator as a constructor argument and is exercised with fakes.

The four test files that need real models (`test_breeze_engine`, `test_qwen3_engine`, `test_punct`, `test_vad`) guard themselves with `pytest.mark.skipif` on the corresponding `downloads.*_ready()` check. A fresh checkout has no `models/` directory, so they skip — which is what lets CI run the other 151 tests on a GPU-free runner.

CI also runs `setup.bat` itself and executes the suite with the interpreter it produces. Installing the lock file is not the same thing as the documented install path working, and a first-step failure is the one users never report.

The same principle covers hardware: `tests/test_gpu.py` substitutes a fake CUDA library for `nvcuda.dll`, so every branch of GPU detection — no driver, driver but no device, `cuInit` failure, multiple devices — is exercised on a runner that has no GPU at all.
