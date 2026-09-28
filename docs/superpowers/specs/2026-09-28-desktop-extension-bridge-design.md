# Desktop–extension bridge — design

**Goal:** A mark drawn in the Windows desktop overlay over Chrome uses the page's DOM text and links when the paired Spatial extension is available. The existing UIA/OCR path remains available for other windows and failures.

## Flow

1. The desktop server freezes the screen and sends captured Chrome window titles and bounds to the paired extension. The extension binds a unique active tab only when Chrome also reports a focused window at matching screen bounds, and records its document ID. Blocked, unmatched, or unreadable pages get a protected verdict.
2. After the mark, the server checks the captured window's verdict, then reads UIA candidates if it is safe. The extension reads DOM candidates only from the captured document at the marked viewport position and returns protocol-v3 `CandidateObject` values in captured-monitor pixels.
3. The server prefers valid DOM candidates. A safe page with an empty DOM result retains UIA/OCR fallback. If the paired tab navigates or the extension cannot attest the page during a mark, the window is protected before UIA runs. Without a paired extension at capture time, the desktop retains its existing UIA/OCR behavior. The answer API and desktop panel remain unchanged.

## Boundaries

- The connection opens only after the extension has consent and a paired API token, and only to a loopback server. The WebSocket authenticates the token before it accepts bridge work. A browser page never receives the token or bridge messages.
- No DOM read occurs on blocked sites, browser internal pages, or sensitive windows. The extension sends only shortlisted text and metadata for the marked region, with the same 800-character text cap as its own mark flow; no new pixels are sent.
- Screen-to-viewport conversion uses the captured window bounds and the tab's current device pixel ratio. A mark outside the viewport yields no DOM candidates. An unmatched or ambiguous active tab is protected while paired. Mixed-DPI placement still needs physical hardware testing.
- The extension service worker exchanges a heartbeat within Chrome's 30-second idle window and reconnects after a server restart. Chrome 116 is already the extension minimum.

## Checks

- Server tests cover authentication, a returned DOM candidate, timeout/disconnect fallback, and protected windows.
- Extension tests cover physical-pixel/viewport conversion and a mismatched or blocked tab.
- Manual check: mark text and a link in Chrome, compare the desktop panel target to the page; verify fallback with the extension disabled and protection on a blocked site.
