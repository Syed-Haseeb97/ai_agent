# AI Screen Assistant – Free Windows 11 MVP

A lightweight floating circular AI assistant that sits in the corner of your screen.

**How it works**
1. Click the circle (or press **Ctrl + Alt + Space**)
2. Speak your question
3. It captures your current screen, sends the screenshot + your words to **Gemini free tier**
4. Gemini sees what is on your screen and answers
5. The reply is spoken out loud and shown in a small card

Completely free for personal MVP use. No local AI models required (works on low-end laptops).

---

## Requirements
- Windows 10 / 11
- Python 3.10 or newer
- A free Gemini API key from [Google AI Studio](https://aistudio.google.com/app/apikey) (no credit card needed)
- Working microphone

---

## Quick Start

```powershell
# 1. Open PowerShell in this folder
cd path\to\ai_assistant

# 2. Create virtual environment
python -m venv venv
venv\Scripts\activate

# 3. Install PyAudio (the only tricky package on Windows)
pip install pipwin
pipwin install pyaudio

# If pipwin fails, download a matching .whl from:
# https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio
# then: pip install PyAudio‑....whl

# 4. Install the rest
pip install -r requirements.txt

# 5. Add your free Gemini key
copy .env.example .env
notepad .env
# Replace your_gemini_api_key_here with the real key

# 6. Run
python main.py
```

A dark circle with “AI” will appear in the top-right corner.

---

## Usage
- **Click** the circle → it turns green and listens
- **Or** press `Ctrl + Alt + Space`
- Speak clearly (e.g. “What’s on my screen?”, “Summarize this page”, “What error is this?”)
- Wait a few seconds – it will think (blue), then speak the answer and show a text card
- Drag the circle to move it
- Right-click the system tray icon for Show/Hide or Quit

---

## Project Structure
```
ai_assistant/
├── main.py
├── hotkey_manager.py
├── requirements.txt
├── .env.example
├── README.md
├── ui/
│   ├── floating_button.py   # the circle + full pipeline
│   ├── status_popup.py
│   └── response_popup.py
├── voice/
│   ├── listener.py          # free Google Web Speech
│   └── tts.py               # edge-tts → pyttsx3 fallback
├── vision/
│   └── capture.py           # mss + Pillow screenshot
└── ai/
    └── gemini_client.py     # Gemini vision call
```

---

## Notes & Limitations (MVP)
- Uses **Gemini free tier** rate limits. Do not spam requests.
- Screen capture is the primary monitor only (can be extended later).
- Speech recognition needs internet (Google Web Speech).
- TTS prefers `edge-tts` (neural voices); falls back to `pyttsx3` if needed.
- Microphone permission must be allowed in Windows Settings → Privacy → Microphone.
- This is an MVP for testing the idea, not a polished product.

---

## Troubleshooting
| Problem | Fix |
|---------|-----|
| `No module named 'pyaudio'` | Use `pipwin install pyaudio` or install a wheel |
| Mic not detected | Check Windows microphone privacy settings |
| Gemini errors | Verify `.env` key and free-tier quota in AI Studio |
| Circle not visible | Check system tray → Show, or restart |
| Hotkey not working | Run terminal as normal user (not admin) or change hotkey in code |

---

## Next ideas after MVP works
- Active-window capture only
- Click-through mode
- Conversation memory
- Better tray icon
- Multi-monitor support
- Optional web search tool calling when Gemini grounding is available

Enjoy testing!
