# Security Policy

## Reporting a vulnerability

Please report security issues privately via [GitHub's private vulnerability reporting](https://github.com/gavinkao98/ASR/security/advisories/new) rather than opening a public issue.

I'll acknowledge your report within about a week. This is a personal project maintained in spare time, so please calibrate expectations on turnaround accordingly.

## Scope and threat model

This tool is a local Windows utility. It has no server component, no user accounts, and no telemetry. Some notes on what it does touch, since that's where the interesting risk lives:

**Audio never leaves the machine.** Recording is captured, trimmed, and transcribed entirely locally. The only outbound network traffic is downloading model weights from Hugging Face during first-run setup, and `localhost` traffic to the bundled `llama-server` process that runs the Qwen3 engine.

**Transcripts are stored locally.** Recognition history lives in a SQLite database at `data/history.db` (last 200 entries), and logs at `data/logs/asr.log`. Neither is encrypted. Anything you dictate — passwords included — may end up in both. History can be disabled in the settings window. **Please don't dictate credentials.**

**The tool injects text into the focused window via the clipboard.** It briefly writes to the clipboard, sends a paste keystroke, and restores the previous clipboard contents. Consequences worth understanding:

- Any clipboard-monitoring software on the machine can observe transcripts during that window.
- If focus changes between transcription and paste, text can land in the wrong application.
- Windows blocks injection into elevated windows from a non-elevated process. This is a security boundary working correctly — see the README troubleshooting section rather than treating it as a bug.

**A global keyboard hook is installed** to detect the push-to-talk key. It observes key events system-wide; it does not log or transmit them.

**Model weights are downloaded at runtime** from Hugging Face and are not pinned by hash. Supply-chain issues in the upstream model repositories are outside this project's control.

## Out of scope

Reports that amount to "the tool can access the clipboard" or "an administrator could read `history.db`" describe the design, not vulnerabilities. Local attacks requiring an attacker who already has code execution on the machine are likewise out of scope.
