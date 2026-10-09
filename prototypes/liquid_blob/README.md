# Ruby Liquid Blob — isolated prototype

This is a standalone visual playground for Ruby's glossy orb. The same `LiquidBlob` renderer now powers the production floating assistant through `ui/liquid_blob.py`; the playground remains isolated from microphone, Gemini, TTS, and Windows-action logic.

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

Use the buttons at the bottom to preview Idle, Listening, Thinking, Speaking, Happy, Sad, and Error. Thinking is a faceless, fast-spinning glossy sphere. Other states alter gaze, body deformation, color, sheen, and motion. The prototype uses a 30 FPS timer to keep animation work modest on integrated/entry-level graphics hardware.

## Current scope and limitations

- This is a **2D custom-painted, glossy 3D-inspired** character using Qt gradients, highlights, shadows, and an animated organic silhouette.
- It is a visual experiment, not physically simulated fluid or a true 3D renderer.
- Emotional states are manually selectable previews. There is no sentiment inference or emotion detection.
- The production widget uses the same renderer at floating-button size and maps real assistant states to Idle, Listening, Thinking, Speaking, and Error.
- The prototype's Happy and Sad states remain preview-only.
