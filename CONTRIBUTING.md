# Contributing

Thanks for taking an interest. Issues and pull requests are both welcome.

Bug reports and PR descriptions in **English or Traditional Chinese** are equally fine — write in whichever you're more comfortable with.

## Reporting a bug

Because this tool injects text into other applications and touches the clipboard, the surrounding environment matters a lot. Please include:

- Your Windows version, and whether the app is running elevated (as Administrator)
- GPU model and driver version, or "CPU only"
- Which engine was selected (Qwen3 or Breeze)
- **The target application** you were dictating into
- Any antivirus or clipboard-manager software running — these are a recurring source of clipboard and input-injection conflicts
- The relevant portion of `data/logs/asr.log`

## Development setup

```bash
setup.bat
```

That builds `.venv` and installs everything. To run the app from source:

```bash
.venv\Scripts\python main.py
```

## Tests

```bash
.venv\Scripts\python -m pytest
```

The suite needs no GPU and no downloaded models — the four model-backed test files skip themselves when the models are absent. A fresh checkout should show `138 passed, 6 skipped` in a couple of seconds. If you have the models installed locally, all 144 run.

Please add tests for behaviour changes. The existing suite is a good guide to the style: the logic worth testing has been deliberately separated from the Windows API surface, so most of it is testable without a GUI, a microphone, or a model. `app/ptt_logic.py` and `app/postprocess/` are the clearest examples.

## Architecture notes

Read [`docs/architecture.md`](docs/architecture.md) before making a substantial change. Two constraints are load-bearing and easy to break by accident:

1. **NVIDIA DLL injection must happen before `ctranslate2` or `faster_whisper` is imported.** `main.py` does this at module scope, and `tests/conftest.py` imports `main` for the same reason. Don't move it.
2. **Clipboard access belongs in the helper process**, not the main process. `app/clipwin.py` is deliberately dependency-free so both processes can share it. The isolation is what keeps an antivirus conflict from taking down the app.

## Pull requests

- Keep a PR to one logical change.
- Make sure `pytest` passes; CI runs it on `windows-latest` and will tell you if it doesn't.
- Match the surrounding code's style. Comments in this codebase explain *why*, not *what* — the existing ones are worth reading before you add your own.

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE).
