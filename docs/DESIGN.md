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
| Ambiguous | **Built (2026-09-23):** numbered dashed outlines on the top 2–4 candidates + "Did you mean:" chips; clicking re-asks with `target_id`; the pick is logged as a correction (`label`) in the trace |
| Unresolved | "Circle a bit tighter" hint; still answers from crop/OCR if the user insists |

## 3. Desktop (built 2026-09-24, Windows)

- **Freeze-frame overlay:** hotkey captures the monitor under the cursor, shows that still image full-screen
  (dimmed), user draws on it. Nothing moves mid-mark; the overlay can't appear in its own capture.
- **Ask panel:** small floating always-on-top window placed beside the mark (right, else left, else below), shown
  only after candidates are read so it never covers the marked region; Esc/✕ hides it.
- **Dashboard (desktop):** regular window from the app icon/tray: Home (status, activity), Ask logs, Dictation
  logs, Settings. The Ask panel holds only the thread and composer; no status or settings.
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
| 2026-09-23 | Jev on every ask; clarify chips instead of "circle tighter" | Routing saves ~5 s research on most asks; chips turn ambiguity into a one-click correction |
| 2026-09-23 | Hybrid target gate = Jev pick probability ≥ 0.5 (not confidence) | Confidence is diluted by extra options; eval 47/49 → 49/49 |
| 2026-09-24 | Desktop: server owns capture + UIA; Tauri app only draws/asks; per-launch token file | One place for pixels/OS access; screen routes unreachable from web pages |
| 2026-09-24 | Overlay hides itself before candidates are read | UIA point probes hit the topmost window — it must be the user's app, not us |
