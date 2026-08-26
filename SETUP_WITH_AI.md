# Set up Ruby with an AI assistant

Copy the block below and paste it into ChatGPT, Claude, Cursor, Copilot, or any coding agent on the Windows PC where you want Ruby installed.

```text
You are helping me fully set up the Ruby AI Screen Assistant on a Windows PC from GitHub.

Repository:
https://github.com/Syed-Haseeb97/ai_agent

Preferred branch (if available):
feature/f2-2-browser-agent-v2

Otherwise use the default branch.

Goal:
Clone the repo, install all required dependencies, configure the Gemini API key, verify the install, and start the app successfully on THIS Windows machine.

Do the work for me step by step. Prefer PowerShell. If a step fails, diagnose and fix it before continuing. Do not skip verification.

========================
TARGET ENVIRONMENT
========================
- OS: Windows 10/11 (project is Windows-oriented)
- Python: 3.11+ preferred (project has also been used with newer Python; use what is installed if compatible)
- Shell: PowerShell
- Internet required for clone, pip, Playwright browser download, and Gemini API

========================
SETUP STEPS TO PERFORM
========================

1) Prerequisites check
- Confirm Windows PowerShell works
- Confirm Git is installed (`git --version`). If missing, tell me how to install Git for Windows and wait.
- Confirm Python is installed (`python --version` or `py --version`). If missing, tell me how to install Python 3.11+ from python.org with "Add python.exe to PATH" enabled and wait.

2) Clone the repository
- Choose a sensible project folder (for example: %USERPROFILE%\\projects\\ai_agent)
- Clone:
  git clone https://github.com/Syed-Haseeb97/ai_agent.git
  cd ai_agent
- If branch feature/f2-2-browser-agent-v2 exists:
  git fetch origin
  git checkout feature/f2-2-browser-agent-v2

3) Create and activate a virtual environment
  python -m venv venv
  .\\venv\\Scripts\\Activate.ps1
If execution policy blocks activation:
  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
Then activate again.

4) Install Python dependencies
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt

Important package notes from this project:
- Uses google-genai (NOT the deprecated google-generativeai)
- Uses playwright for browser automation
- UI uses PyQt6
- Voice uses SpeechRecognition, edge-tts, optional pyttsx3
- Microphone on some Python builds may need PyAudioWPatch (documented in requirements.txt)

5) Install Playwright browser runtime
  python -m playwright install chromium
If Chrome is already installed on the machine, the app can also try to use it, but Chromium via Playwright must still be installed as a reliable fallback.

6) Configure environment variables
- Copy .env.example to .env
- Open .env and set:
  GEMINI_API_KEY=<my real key>
- Get a free key from: https://aistudio.google.com/app/apikey
- Never commit .env to Git
- Optional:
  GEMINI_MODEL=gemini-2.5-flash

7) Optional external tools (install only if I want those features)
- FFmpeg (recommended): install a Windows build that provides ffmpeg.exe, ffprobe.exe, and ffplay.exe on PATH.
  Used for screen recording and smoother Edge-TTS playback.
- Optional pip packages:
  python -m pip install pyautogui
  python -m pip install openwakeword numpy
  (wake-word support is optional and may be platform-sensitive)

8) Automated setup script alternative
If preferred, from the repo root after clone:
  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
  .\\setup_windows.ps1
Then still create/configure .env with GEMINI_API_KEY.

9) Verify installation
Run these checks with the venv activated:
  python -c "import PyQt6; print('PyQt6 OK')"
  python -c "import playwright; print('Playwright OK')"
  python -c "from google import genai; print('google-genai OK')"
  python -c "from dotenv import load_dotenv; load_dotenv(); import os; print('GEMINI_API_KEY set' if os.getenv('GEMINI_API_KEY') and os.getenv('GEMINI_API_KEY') != 'your_gemini_api_key_here' else 'GEMINI_API_KEY MISSING')"
  python -m unittest tests.test_browser_agent -v

10) Start the app
  .\\venv\\Scripts\\Activate.ps1
  python main.py

Expected result:
- A floating robot assistant button appears on screen
- Tray icon / floating UI is available
- I can click the button or use the hotkey/voice flow
- Browser commands can open sites and search (Playwright visible browser)
- Gemini answers questions using a screenshot of the screen when needed

========================
HOW THE APP WORKS (so you can debug)
========================
- Entry point: main.py
- Floating UI: ui/floating_button.py
- Local Windows actions + browser routing: actions/windows_actions.py
- Browser automation: actions/browser_actions.py (Playwright on a dedicated worker thread)
- Browser command planner: actions/browser_agent.py
- Gemini client: ai/gemini_client.py (google-genai SDK)
- Voice TTS: voice/tts.py (edge-tts + optional ffplay streaming; pyttsx3 fallback)
- Speech input: voice/listener.py
- Screenshots for Gemini: vision/capture.py

Useful browser command examples after startup:
  open youtube
  search for bbs
  open youtube and search for bbs
  open github
  open vercel
  open notion
  open gemini
  open perplexity

========================
COMMON FAILURES AND FIXES
========================
- "GEMINI_API_KEY is missing": create .env from .env.example and set a real key
- Playwright browser fails to start: run `python -m playwright install chromium`
- Microphone not working: install PyAudioWPatch or a compatible PyAudio build for this Python version
- TTS warning / no speech: install edge-tts; optional ffplay from FFmpeg for streaming playback
- PowerShell says scripts are disabled: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
- UI does not appear: confirm PyQt6 installed inside the venv and start with `python main.py` from the activated venv
- Browser follow-up commands fail: ensure you are on a branch that includes the worker-thread BrowserActions fix (feature/f2-2-browser-agent-v2)

========================
DONE CRITERIA
========================
Report back with:
1. Python version used
2. Branch checked out
3. Whether venv + requirements + Playwright install succeeded
4. Whether GEMINI_API_KEY is configured (do NOT print the key)
5. Unit test result for tests.test_browser_agent
6. Whether python main.py launched successfully
7. Any remaining issues and exact fix commands
```
