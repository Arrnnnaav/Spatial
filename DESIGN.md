# Design

*Interaction design, UI language and key design decisions. Living document; add a line to the decision log
whenever a design choice is made or reversed.*
**Last updated:** 2026-09-23

## 1. Core interaction

```
hotkey ─▶ overlay (dim + tools) ─▶ draw mark(s) ─▶ ask panel opens next to mark ─▶ type / speak
       ─▶ resolved target pulses (highlight) ─▶ streamed answer ─▶ follow-ups keep the same target
```

- **Marks:** pen (freehand → polygon; closed stroke = region, open stroke = padded pointer), circle, box, point.
- **Roles:** Reference (default), Source, Target — for "how does A lead to B?" / compare.
- **Ask panel:** opens right of the mark, flips left if no room; Enter sends, Shift+Enter newline; mic;
  speaker (read aloud); research toggle ("🔎 Verify with sources", default on); level (eli5 / student / expert).
- **Answer meta line:** provider/model, anchors used, vision/OCR, confidence, diagram, level.
- **Esc / Done** closes; new mark starts a new conversation; follow-ups inherit the target.

## 2. Confidence UX (target)

| Band | Behaviour |
|---|---|
| Confident | Highlight target, answer directly |
| Ambiguous | Numbered overlays on the top 2–4 candidates: "Did you mean 1, 2 or 3?" — click or say the number; the choice is logged as a correction |
| Unresolved | "Circle a bit tighter" hint; still answers from crop/OCR if the user insists |

## 3. Desktop (planned)

- **Freeze-frame overlay:** hotkey captures the monitor under the cursor, shows that still image full-screen
  (dimmed), user draws on it. Nothing moves mid-mark; the overlay can't appear in its own capture.
- **Ask panel:** small floating always-on-top window anchored near the mark; dismiss restores the live screen.
- **Tray icon:** status (server up, provider), settings, trace-log toggle, quit.

## 4. Visual language

| Token | Value |
|---|---|
| Stroke / Source | `#ff3d7f` |
| Target | `#2f7cf6` |
| Highlight (resolved) | `#00d4aa` |
| Font | `system-ui`, 13–14 px base |
| Spacing | 8 px grid |
| Radius | 6–14 px |
| Touch targets | ≥ 44 × 44 px |

## 5. Decision log

| Date | Decision | Why |
|---|---|---|
| 2026-09-23 | Spatial becomes independent of StudyOS | One source of truth; desktop client would triple the sync burden |
| 2026-09-23 | OS-level next: Windows first, stack must port to macOS → Tauri | User choice B; Tauri shares web UI, small installer |
| 2026-09-23 | Freeze-frame overlay on desktop | Stable geometry, no self-capture, screenshot + UIA snapshot aligned |
| 2026-09-23 | Jev as System-One helper, never the answerer; Laya evaluated on same protocol | Jev: cheap/fast typed judgments; Laya: open weights, needs fine-tuning for element selection |
| 2026-09-23 | Cloud APIs acceptable; local/privacy-first deprioritised | User priority: accuracy + reach |
| 2026-09-23 | Trace log = metadata + resolution trace, no pixels, opt-in | Enough for replay/eval/training without storing screenshots |
