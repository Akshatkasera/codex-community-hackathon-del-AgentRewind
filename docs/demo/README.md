# Demo Video Guide

This folder contains everything needed to create a short narrated demo video for AgentRewind.

## Files

- `importable_support_refund_trace.json` - the trace file uploaded during the demo
- `demo-video-script.md` - the visual beat sheet and spoken script
- `demo-video-narration.txt` - the exact narration text sent to OpenAI TTS
- `demo-video-config.json` - timing, TTS, and output settings for the generator

## What the generator does

`npm run demo:video` from the `frontend` folder will:

1. Build the frontend
2. Start the backend in mock mode
3. Open AgentRewind in a recorded Playwright browser
4. Upload the demo trace file through the UI
5. Wait for the diagnosis to appear
6. Replace the broken retrieval prompt with the corrected prompt
7. Replay the run from that step
8. Generate narration audio with OpenAI TTS
9. Merge the browser recording and narration into a final MP4

## Run it

```powershell
cd D:\AgentRewind\frontend
npm install
npm run demo:video
```

## Output

The generated files are written to `docs/demo-output/`:

- `agentrewind-demo.mp4` - final narrated demo video
- `agentrewind-demo-narration.mp3` - narration audio from OpenAI TTS
- `agentrewind-demo-raw.webm` - raw browser recording before muxing

## OpenAI key resolution

The narration generator looks for an API key in this order:

1. `OPENAI_API_KEY` in the shell environment
2. `backend/.env`
3. the prompt path configured in `backend/.env`

The backend itself runs in mock mode for the demo so the UI is deterministic. OpenAI is only used for the narration track.
