# Voice Input — offline Traditional Chinese speech-to-text for Windows

[![CI](https://github.com/gavinkao98/ASR/actions/workflows/ci.yml/badge.svg)](https://github.com/gavinkao98/ASR/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)

**English** ｜ [繁體中文](README.zh-TW.md)

Hold a key, talk, release — the text lands at your cursor in **any** Windows application. Everything runs on your own machine: no account, no cloud API, no audio ever leaves the computer (the only network access is the one-time model download during setup).

Built for people who write Traditional Chinese but whose sentences are full of English technical terms. Output is punctuated Traditional Chinese, and terms like `API`, `benchmark`, or `Kubernetes` keep their correct spelling instead of being mangled into phonetic Chinese.

## Why this exists

Windows' built-in dictation and the mainstream cloud dictation tools are a poor fit for Traditional Chinese developers on three counts:

- **They send your audio to a server.** That rules them out for anyone handling client work, medical notes, legal drafts, or internal code discussions.
- **They target Simplified Chinese.** Traditional Chinese output is an afterthought when it exists at all, and locale-specific vocabulary (台灣用語) gets converted incorrectly.
- **They destroy code-switched English.** Saying "先跑 benchmark 再看 API 延遲" typically comes back with the English words transcribed phonetically.

This project fixes all three by running a local ASR model with a post-processing chain tuned for zh-TW, and by injecting the result into whatever window currently has focus — so it works in LINE, a browser address bar, Word, an IDE, or a terminal without any per-app integration.

## Quick start

Requires Windows 10/11 and Python 3.12. An NVIDIA GPU makes recognition faster but is **not** required — CPU works, just slower.

1. **Double-click `setup.bat`** — creates an isolated virtual environment and installs dependencies. Needs a network connection.
2. **Double-click `啟動語音輸入.vbs`** — starts the app. It runs silently in the system tray, with no console window.
3. A **first-run wizard** appears once, walking you through an environment check, model download (Qwen3-ASR-1.7B, the llama-server runtime, and the VAD model), and a microphone test.

Then, anywhere you can see a text cursor:

1. **Hold `CapsLock`** and speak — a small recording indicator appears in the screen corner.
2. **Release** — the transcript is pasted at the cursor.

A quick *tap* of `CapsLock` still toggles capitals as usual. Only a sustained *hold* triggers recording, so the two uses never collide.

Prefer a desktop shortcut? Run:

```bash
.venv\Scripts\python scripts\make_shortcut.py
```

## How it works

```
CapsLock hold ──► Recorder ──► VAD trim ──► ASR engine ──► post-process chain ──► inject at cursor
                 (sounddevice)  (silero)   (Qwen3/Breeze)  (punct→tradify→        (clipboard helper
                                                            digits→hotwords→       subprocess)
                                                            repeat-guard)
```

A few design decisions worth calling out:

- **Push-to-talk is a state machine, not a keypress handler.** `app/ptt_logic.py` distinguishes tap from hold with a configurable threshold, and re-emits the original keystroke on a cancelled tap so `CapsLock` keeps its normal behaviour.
- **Text injection goes through the clipboard, and the clipboard is restored afterwards** — not just text, but images, files, and rich text (Word/HTML) come back byte-identical.
- **Clipboard I/O runs in a separate helper process** (`app/clipboard_helper.py`, using the dependency-free `app/clipwin.py` ctypes layer). Antivirus and clipboard-manager software are notorious for destabilising in-process clipboard access; isolating it means a conflict kills only the disposable helper, which respawns, while the main process and the paste result are unaffected.
- **The post-processing chain is composable and engine-aware** (`app/postprocess/chain.py`): it only adds punctuation if the engine doesn't produce it natively, only converts Simplified→Traditional if the engine emits Simplified, and so on.

### Recognition engines

| Engine | Notes |
|---|---|
| **Qwen3-ASR-1.7B** (default) | Native punctuation, automatic Simplified→Traditional conversion, strong code-switched English |
| **Breeze-ASR-25** | Alternative engine, switchable at runtime from the settings window |

Engines implement a small interface in `app/engines/base.py`, so adding a third is a self-contained change.

## Configuration

Left-click the tray icon for settings; right-click for pause/resume and quit. The settings window has five tabs:

| Tab | What it controls |
|---|---|
| **一般** (General) | Launch at login, notification sounds, paste mode, verbatim output, Chinese numerals → Arabic digits (「四零九六」→ 4096), skip punctuation for short phrases, microphone selection |
| **熱鍵** (Hotkey) | Which key triggers recording, and the hold-vs-tap threshold |
| **模型** (Models) | Switch engines, or download one that isn't installed yet |
| **熱詞** (Hotwords) | Custom correction rules for consistently misheard terms |
| **歷史** (History) | The last 200 transcripts |

Hotword rules are one per line, `misheard=correct`, with `#` for comments:

```
派森=Python
```

Changes take effect immediately — no restart.

## Development

```bash
.venv\Scripts\python -m pytest
```

144 tests cover the push-to-talk state machine, the post-processing chain, both engine adapters, clipboard save/restore, config, history, and downloads.

Six of them exercise real models (Breeze, Qwen3, punctuation, VAD) and skip automatically when those aren't downloaded. So a fresh checkout runs **138 tests in ~2.5 seconds with no GPU and no model downloads**, which is exactly what CI does on `windows-latest` / Python 3.12. With the models present locally, all 144 run in about 13 seconds.

[`docs/architecture.md`](docs/architecture.md) explains the threading model, the clipboard-isolation design, and the CUDA DLL loading order — read it before making a substantial change. See [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

## Troubleshooting

**Text won't paste into some windows.** If the target window runs elevated (as Administrator), Windows blocks input from a non-elevated process. This is a Windows security boundary, not a bug. The text is already on your clipboard — either press `Ctrl+V` manually, or start this tool as Administrator too.

**cuDNN / CUDA errors.** Update your GPU driver, then re-run `setup.bat`.

**The first sentence after startup is slow.** Idle GPUs downclock; the first transcription can take an extra 0.1–0.3s. Subsequent ones are back to full speed.

**One clipboard caveat.** Restoring the clipboard cannot preserve *advanced paste state* — for example, Excel's marching-ants marquee after a copy is cleared. Any clipboard modification does this on Windows; it isn't specific to this tool.

## License

[MIT](LICENSE).

Recognition models are downloaded from their original publishers at first run and are **not** redistributed by this repository; they remain under their own respective licenses.
