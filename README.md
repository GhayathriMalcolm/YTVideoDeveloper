# YT Video Developer

A local app that automates your YouTube content pipeline:

1. You give it a topic -> Claude writes a narration script following your rules and gives you a downloadable `.txt`.
2. You paste that script into your voiceover tool and upload the resulting MP3 -> local Whisper transcribes it into a timestamped script.
3. Claude turns every timestamp line into a detailed doodle-style image prompt -> downloadable `.txt`.
4. You generate one image per prompt in Google Flow (manual, no public API available), then upload them all back into the app.
5. FFmpeg automatically assembles the uploaded images + narration audio into a finished MP4, timed to the transcript.
6. Claude generates 5-8 viral titles, an optimized description, and SEO tags, ready to paste into YouTube.

## Setup

1. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill in your key:

   ```bash
   copy .env.example .env
   ```

   You need `ANTHROPIC_API_KEY` (required, powers script/prompt/metadata generation).

3. Run the app:

   ```bash
   python run.py
   ```

   This starts a local server at `http://127.0.0.1:8000` and opens it in your browser.

## Standalone app (no Python required)

For day-to-day use without a terminal, build a self-contained `.exe`:

```bash
.\.venv\Scripts\python.exe -m PyInstaller run.py --name "YTVideoDeveloper" --onedir --console --add-data "web;web" --collect-all faster_whisper --collect-all ctranslate2 --collect-all onnxruntime --collect-all tokenizers --collect-all huggingface_hub --noconfirm
```

Then copy your `.env` into the output folder:

```bash
copy .env "dist\YTVideoDeveloper\.env"
```

The finished app is `dist\YTVideoDeveloper\YTVideoDeveloper.exe` — double-click it to launch (a console window opens showing logs, then your browser opens automatically). To share or move it, copy the entire `dist\YTVideoDeveloper\` folder — `.env` and everything the exe needs travels with it. Projects are stored in a `projects\` folder created next to the exe, separate from the `projects\` folder used when running via `python run.py`.

Rebuild the same way any time you change the app's code — PyInstaller re-bundles everything from scratch in about a minute.

## Notes

- Whisper transcription runs fully locally and offline once the model is downloaded on first use (default size: `small`). Change `WHISPER_MODEL_SIZE` in `.env` for a speed/accuracy tradeoff (`tiny`, `base`, `small`, `medium`, `large-v3`).
- Each project (one per topic) lives in its own folder under `projects/<topic-slug>/` with the script, audio, transcript, prompts, images, and final video — nothing is overwritten between runs.
- When uploading images, select all of them at once (multi-select in the file picker) and upload in one go. The app sorts the selected files by filename (natural/numeric order, e.g. `2.png` before `10.png`) and maps them in that order to the prompts, which are already in chronological timestamp order — so name your downloaded Google Flow images sequentially (e.g. `0001.png`, `0002.png`, ...) to guarantee correct ordering. The count must match exactly: one image per prompt.
- Once uploaded, the app saves each image under `projects/<topic-slug>/images/` renamed to its matching timestamp, e.g. `00-11.png` for the `[00:11]` prompt (colons aren't valid in Windows filenames, so `:` becomes `-`). This makes it easy to spot-check an image against its prompt just by the filename.
