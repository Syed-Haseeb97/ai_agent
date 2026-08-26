# Ruby — AI Screen Assistant

Ruby is a Windows desktop AI assistant with a floating UI, voice input/output, Gemini-powered responses, local Windows actions, and Playwright-based browser automation.

## Functional runtime requirements

### 1. Windows
- **Windows 11** is the target platform.
- The project uses Windows-specific application/system actions, so it is not currently a cross-platform application.

### 2. Python
- Python **3.14** is currently used by the project environment.
- A Python virtual environment (`venv`) is recommended and is created automatically by `setup_windows.ps1` when needed.

Create/activate the environment manually from the project directory if required:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3. Python packages

The core Python dependencies are listed in `requirements.txt` and include:

- **PyQt6** — desktop/floating UI.
- **mss** — screen capture.
- **Pillow** — image/screenshot handling.
- **SpeechRecognition** — speech-to-text interface.
- **edge-tts** — text-to-speech.
- **google-genai** — current Gemini API integration.
- **pynput** — keyboard/hotkey handling.
- **python-dotenv** — `.env` configuration.
- **pyttsx3** — local TTS support/fallback.
- **playwright** — browser automation.
- **PyAudioWPatch** — microphone/audio input support used by the current Windows/Python 3.14 setup.

Install the project's Python requirements with:

```powershell
python -m pip install -r requirements.txt
```

> The project previously used `google-generativeai`; it has been migrated to Google's current `google-genai` SDK. Do not reinstall the deprecated package unless you are working on legacy code outside this repository.

> `requirements.txt` also documents optional packages for specific features. Keep those optional unless you enable the corresponding feature.

## External software / downloads

These are **not ordinary Python dependencies** and must be installed separately when the corresponding functionality is enabled.

### FFmpeg — required for F5 and TTS streaming optimization

Install a **pre-built Windows FFmpeg package** containing:

```text
ffmpeg.exe
ffprobe.exe
ffplay.exe
```

Add the directory containing those executables (normally `...\bin`) to the Windows `PATH`.

Ruby uses:

- `ffmpeg` for screen recording (F5).
- `ffplay` for low-latency TTS playback/P7 when available.

Verify from PowerShell:

```powershell
ffmpeg -version
ffplay -version
```

### Playwright Chromium — browser automation

Browser automation is now part of Ruby's supported runtime. The Python Playwright package is included in `requirements.txt`; the Chromium browser runtime must also be installed:

```powershell
python -m playwright install chromium
```

Ruby uses a visible persistent browser context for browser actions. It first attempts the installed Windows Chrome executable when available and falls back to a dedicated Playwright Chromium profile if Chrome cannot be started. Browser profiles are kept separate from the user's normal Chrome profile to reduce profile-lock and startup conflicts.

Browser automation supports generic website opening and search rather than relying on a fixed website whitelist. Known services can have specialized interaction logic where a site requires it (for example, YouTube video selection or Spotify playback), while arbitrary destinations can still be resolved without adding a new hard-coded site entry.

### PyAutoGUI — screen/mouse/keyboard automation

Optional for F12 coordinate-based screen interaction:

```powershell
python -m pip install pyautogui
```

It provides mouse/keyboard automation and depends on supporting Python packages such as Pillow, PyGetWindow, PyScreeze, PyMsgBox, PyTweening, MouseInfo, PyRect, and Pyperclip.

### openWakeWord + NumPy — optional wake word

F6 uses local wake-word detection when enabled. Install the compatible packages:

```powershell
python -m pip install openwakeword numpy
```

A compatible custom **“Hey Ruby”** openWakeWord model must also be supplied through `RUBY_WAKE_MODEL`. The project does **not** claim that openWakeWord itself provides a stock “Hey Ruby” model.

The wake-word implementation also uses **PyAudioWPatch** for microphone capture.

## API / configuration

Ruby requires a Gemini API key for Gemini-powered AI functionality. Copy `.env.example` to `.env` and set:

```text
GEMINI_API_KEY=your_gemini_api_key_here
```

The repository's `.env.example` documents the Gemini API-key setting. **Do not commit your real API key.**

Optional environment variables used by advanced features include:

```text
RUBY_WAKE_WORD=1
RUBY_WAKE_MODEL=path-to-your-hey-ruby-model
```

## Feature-specific external requirements

| Feature | External requirement |
|---|---|
| Core UI / voice assistant | Python + packages in `requirements.txt` + Gemini API key |
| P7 TTS streaming | FFmpeg `ffplay` on PATH when available |
| F2.2 Browser agent | Playwright + Chromium browser runtime |
| F2.2 YouTube latest | Browser agent + Playwright/Chromium; YouTube-specific DOM interaction |
| F2.2 Generic websites | Browser agent + Playwright/Chromium; no per-site package required |
| F3 Screenshot | Built-in/project screen-capture dependencies (`mss`, Pillow) |
| F4 Windows startup | Windows startup/task mechanisms; no extra Python package required |
| F5 Screen recording | FFmpeg `ffmpeg` on PATH |
| F6 Hey Ruby | openWakeWord + NumPy + PyAudioWPatch + compatible custom wake-word model |
| F7 File basics | Windows + Python standard library/project action layer |
| F8 App control | Windows + project action layer |
| F9 System settings | Windows + project action layer |
| F10 Reminders | Project Python code; no separate external service required |
| F11 Clipboard | Project/Python UI dependencies |
| F12 Screen clicks | PyAutoGUI |
| F13 Multi-step commands | Project action executor; browser steps can use Playwright |
| F14 Personality/voice preferences | Project preference system + installed voice dependencies |
| F15 Memory | Project memory system + Gemini for relevant AI context |

## Quick setup

The recommended Windows setup is:

```powershell
cd "D:\projects\onscreen ai agent\ai_assistant"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\setup_windows.ps1
```

The setup script creates the project virtual environment when necessary, installs `requirements.txt`, installs the Playwright Chromium runtime, and verifies the key runtime dependencies.

If you prefer to perform the setup manually:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium
```

Then install optional external components needed for your setup:

```powershell
# Screen/mouse automation
python -m pip install pyautogui

# Optional wake-word support
python -m pip install openwakeword numpy
```

Install FFmpeg separately and make sure `ffmpeg` and `ffplay` work from a new PowerShell window.

Start Ruby with:

```powershell
.\venv\Scripts\Activate.ps1
python main.py
```

## Browser agent examples

Browser commands are intended to be natural-language driven. The browser layer is not limited to a hard-coded list of websites.

Examples:

```text
open github
open youtube and search for bbs
open instagram and search for ronaldo
open notion
open gemini
open perplexity
open notion and search for project management
```

Site-specific behavior is used only when interaction requires knowledge of a site's DOM or controls. For example, YouTube can use specialized logic to locate the latest uploaded video, while ordinary website navigation is handled generically.

## Safety / compatibility notes

- This is a **personal Windows assistant** and some actions directly control the local computer.
- Keep API keys and personal configuration out of Git.
- Browser automation uses a dedicated persistent profile and may fall back from installed Chrome to Playwright Chromium when necessary.
- Optional automation components should be enabled/tested one feature at a time so they do not interfere with the stable voice/UI pipeline.
- F6 wake-word support is optional and depends on a compatible local model.
- Browser interactions depend on third-party website availability and may require site-specific maintenance when websites change their DOM or authentication flows.
