# Ruby Liquid Blob — isolated prototype

This is a standalone visual playground for Ruby's future floating assistant character. It does **not** replace or import the production assistant, and it does not connect to the microphone, Gemini, TTS, or Windows actions.

## Requirements

- Windows 11
- Python 3.10+
- PyQt6

Install the only dependency in your existing project virtual environment:

```powershell
python -m pip install PyQt6
```

## Run

From the repository root:

```powershell
python prototypes/liquid_blob/prototype.py
```

Or from this directory:

```powershell
python prototype.py
```

## Try the states

Use the buttons at the bottom to preview Idle, Listening, Thinking, Speaking, Happy, Sad, and Error. Thinking moves the eyes and changes their shape; other states alter gaze, body deformation, glow, and motion. The prototype uses a 30 FPS timer to keep animation work modest on integrated/entry-level graphics hardware.

## Current scope and limitations

- This is a **2D custom-painted, glossy 3D-inspired** character using Qt gradients, highlights, shadows, and an animated organic silhouette.
- It is a visual experiment, not physically simulated fluid or a true 3D renderer.
- Emotional states are manually selectable previews. There is no sentiment inference or emotion detection.
- No existing production files are modified by this prototype.
- Before integration, inspect it on the target Windows laptop and tune motion, transparency, scaling, and resource use.
