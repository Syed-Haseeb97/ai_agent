# Best Working MVP Checkpoint

**Date:** 2026-08-26

This checkpoint marks the best verified working state of the AI Screen Assistant so far.

## Stability rule
Future features should be implemented without disturbing this baseline. Prefer isolated changes and one feature per commit so changes can be reverted safely.

## Verified working areas
- Voice input
- Persistent chatbot-style text input
- Gemini screen/vision pipeline
- TTS output and interruption
- Correct response/history synchronization
- Persistent conversation history
- Windows action execution
- Website aliases
- YouTube search commands
- Close/open Windows application commands
- Animated floating assistant UI

## Known future work
- F2.2: play the latest matching YouTube video
- Additional Windows actions

This branch is a safety checkpoint. The `main` branch may continue evolving; this branch should remain unchanged unless deliberately replaced with a newer known-good checkpoint.
