# Ruby — AI Screen Assistant

Ruby is a Windows desktop AI assistant with a floating UI, voice input/output, Gemini-powered responses, and local Windows actions.

> 🚧 **Active development:** The `feature/amazon-connector` branch contains the beginning of Ruby's Amazon.in integration. This work is being developed and tested separately before any merge into `main`.

## Functional runtime requirements

### 1. Windows
- **Windows 11** is the target platform.
- The project uses Windows-specific application/system actions, so it is not currently a cross-platform application.

### 2. Python
- Python **3.14** is currently used by the project environment.
- A Python virtual environment (`venv`) is recommended.

Create/activate the environment from the project directory:

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
- **google-generativeai** — Gemini API integration.
- **pynput** — keyboard/hotkey handling.
- **python-dotenv** — `.env` configuration.
- **pyttsx3** — local TTS support/fallback.
- **PyAudioWPatch** — microphone/audio input support used by the current Windows/Python 3.14 setup.

Install the project's Python requirements with:

```powershell
python -m pip install -r requirements.txt
```

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

### Chromium / Playwright — browser automation

For browser automation features, Ruby uses the **Python Playwright package** and its browser runtime. Install them inside the project's virtual environment:

```powershell
python -m pip install playwright
python -m playwright install chromium
```

This provides a controlled Chromium browser for browser-based automation such as opening sites, searching, and future multi-step web interactions.

> Playwright/Chromium are now included in `requirements.txt` for the Amazon connector work. The Chromium browser binary still needs to be installed separately with `python -m playwright install chromium`.

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

## Amazon.in connector — 🚧 In development

Ruby is being extended with a local Amazon.in connector so the assistant can eventually interact with the user's own Amazon account through controlled browser automation.

### Planned capabilities

- View recent Amazon.in orders.
- Find an order by product/order information.
- Read order and delivery status.
- Track an order.
- Cancel an order **only after explicit user confirmation**.
- Future shopping/order capabilities will use additional confirmation safeguards.

### Architecture

```text
Ruby / Gemini
      │
      ▼
Amazon tool layer
      │
      ▼
Local Python service
      │
      ▼
AmazonConnector
      │
      ▼
Playwright
      │
      ▼
Dedicated Chromium profile
      │
      ▼
Amazon.in
```

The connector uses a **dedicated Playwright browser profile** rather than the user's normal Chrome profile. Amazon credentials are not stored in Ruby, `.env`, or the repository. The user logs into Amazon manually in the dedicated browser profile.

The authenticated profile must never be committed to Git:

```text
data/amazon/browser-profile/
```

### Current development status

The Amazon connector is intentionally being implemented in layers:

1. Dedicated browser profile and manual Amazon login.
2. Read-only order retrieval.
3. Order lookup.
4. Tracking/status retrieval.
5. Cancellation workflow with explicit confirmation.
6. Ruby/Gemini tool integration.
7. End-to-end testing with the existing assistant.
8. Review and cleanup.
9. Merge into `main` only after testing is successful.

> **Important:** Amazon's website UI can change, so browser selectors and workflows must be tested against the current Amazon.in interface. CAPTCHA or other security/anti-bot mechanisms must not be bypassed.

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
| P7 TTS streaming | FFmpeg `ffplay` on PATH |
| F2.2 YouTube latest | Browser; Playwright/Chromium for deeper browser automation |
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
| Amazon.in connector | Playwright + Chromium + dedicated authenticated browser profile |

## Quick setup

```powershell
cd "D:\projects\onscreen ai agent\ai_assistant"
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Then install optional external components needed for your setup:

```powershell
# Browser automation / Amazon connector
python -m playwright install chromium

# Screen/mouse automation
python -m pip install pyautogui
```

Install FFmpeg separately and make sure `ffmpeg` and `ffplay` work from a new PowerShell window.

## API / service development

The Amazon connector includes a local service intended to expose safe, explicit operations to Ruby. When the connector is ready for local testing, it can be started with:

```powershell
uvicorn services.amazon_server:app --host 127.0.0.1 --port 8765
```

The service is intentionally bound to `127.0.0.1` and should not be exposed publicly.

## Safety / compatibility notes

- This is a **personal Windows assistant** and some actions directly control the local computer.
- Keep API keys, Amazon authentication state, and personal configuration out of Git.
- Optional automation components should be enabled/tested one feature at a time so they do not interfere with the stable voice/UI pipeline.
- F6 wake-word support is optional and depends on a compatible local model.
- Amazon destructive actions such as cancellation require explicit confirmation.
- Browser automation must not bypass CAPTCHA, MFA, anti-bot protections, or other Amazon security controls.
- Amazon connector changes are developed on a feature branch and should be merged into `main` only after successful testing and review.
