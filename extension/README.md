# Spatial — browser extension

Circle anything you are reading — a website, a web app, a PDF (online or downloaded) — and ask about exactly
that region. Talks to the local server in `../server` (default `http://127.0.0.1:8787`).

## Install (Chrome / Edge / Brave, unpacked)

1. `chrome://extensions` → enable **Developer mode** → **Load unpacked** → pick this folder.
2. For downloaded PDFs (`file:///…pdf`) open the extension's details and enable **Allow access to file URLs**.
3. Click the icon: it shows which providers the server has ready, lets you pick one, choose the privacy
   level, and turn on automatic read-aloud.

## Use

- **Alt+Shift+A** (or icon → *Start marking on this tab*).
- Scribble a circle with the pen (default), or use Circle/Box. Draw more marks if needed.
- Type the question, or press 🎤 and speak: audio is transcribed on the server by faster-whisper (CPU);
  if the server has no STT the browser's Web Speech API is used.
- 🔊 *Read aloud* speaks the answer with pocket-tts on the server. Follow-ups reuse the same mark.
- **Esc** closes, **Clear** starts a fresh context. PDFs open in the bundled pdf.js viewer automatically.

## What gets sent

Marks (viewport coordinates), the DOM/PDF text under the mark, page title/URL, and depending on the privacy
setting a crop of the marked region (default), only text, or the whole visible tab. Nothing acts on the page.

## Development

```bash
node --test tests/geometry.test.mjs
python -m http.server 5173     # then open http://localhost:5173/dev/harness.html with the server running
```

`vendor/` holds pdf.js 4.10.38 (Apache-2.0, see `vendor/LICENSE`).
