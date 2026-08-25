# Ruby feature map

## Current additions
- **P7** TTS streaming: when `ffplay` is available, Edge TTS audio starts playing while it is still being generated.
- **F2.2** YouTube latest: opens a YouTube search with the upload-date filter so newest matching videos are first.
- **F3** Full desktop screenshot: `D:\screen_shots`.
- **F4** Startup: say `enable startup` / `start with Windows` or `disable startup`.
- **F5** Screen recording: say `start screen recording` / `stop screen recording`; requires ffmpeg.
- **F6** Wake word: optional local service; enable with `enable wake word`. A compatible custom `Hey Ruby` openWakeWord model can be supplied with `RUBY_WAKE_MODEL`.
- **F7** File basics: open/find files in common user folders.
- **F8** App control: existing open/close allowlist remains the execution layer.
- **F9** System settings: Bluetooth, Wi-Fi, sound, display settings.
- **F10** Timed reminders: `remind me in 10 minutes to stretch`.
- **F11** Clipboard reading: `summarize my clipboard`.
- **F12** Screen clicks: explicit coordinates such as `click 800,450` when pyautogui is installed.
- **F13** Multi-step commands: chains separated by `then` / `and then` are executed through the existing allowlisted action executor.
- **F14** Personality/voice preferences: `set personality to concise` and `set voice to british`.
- **F15** Memory: `remember that ...` and `what do you remember`; saved memory is supplied to Gemini when relevant.

## External requirements
- F5: install FFmpeg so both `ffmpeg` and `ffplay` are on PATH.
- F6: install compatible `openwakeword`/`numpy` and provide a compatible custom wake-word model for `Hey Ruby`.
- F12: install `pyautogui` if coordinate clicking is desired.

These features are deliberately isolated from the response-history/TTS synchronization code that fixed the stale-answer bug.
