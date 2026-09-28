# Desktop–extension bridge — implementation plan

1. Add the authenticated server WebSocket rendezvous and a bounded candidate request from `/api/desktop/candidates` for safe Chrome windows. Keep UIA/OCR fallback.
2. Connect the extension service worker after pairing; bind a captured Chrome window to a focused active tab using title and bounds, then ask its captured document for DOM candidates.
3. Convert the physical mark to viewport CSS coordinates in the content script, reuse its existing DOM collection, and return v3 candidates in monitor coordinates.
4. Run focused server/extension checks, full release checks, and a real Chrome/desktop pass where available. Update the task board and architecture notes.
