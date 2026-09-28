# PRD — Spatial: Point & Ask

*Living document. Change it when priorities change; note the change in `MEMORY.md`.*
**Last updated:** 2026-09-26

## Problem

Natural language is bad at spatial intent. "The second equation under the grey box" is slow to type and often
misread by an AI. People already know *where* the thing is; they should be able to point at it.
Screenshot-and-ask tools make the user crop, paste and describe, and the model then guesses what part mattered.

## Product

Press a hotkey, circle / box / point at anything, ask (type or speak). Spatial works out **which object** was
meant, shows it (highlight), and answers about exactly that — optionally with cited sources and read aloud.

- **Surfaces today:** web pages and PDFs in Chrome; a Windows desktop prototype over native applications.
- **Surfaces next:** installable Windows release, browser/desktop candidate bridge, and macOS Accessibility support.

## Users (priority order)

1. Students — equations, diagrams, dense textbook/PDF passages.
2. Developers — docs, code, dashboards, error dialogs, IDE panels.
3. Researchers / analysts — charts, tables, papers, reports.
4. Anyone reading unfamiliar UI or content (support, training, accessibility).
5. Later: AI tool builders who want pointing as an input (SDK).

## Goals

| # | Goal | Measure |
|---|---|---|
| G1 | Resolve the right object | Top-1 target accuracy on golden set (baseline set by eval harness; target ≥ 90% web/PDF) |
| G2 | Be fast | Mark → first answer token p50 < 2.5 s (cloud); resolution incl. System One ≤ 1.5 s (≈0.4–0.5 s warm); research only when needed |
| G3 | Show what it understood | Every answer shows the resolved target highlighted; ambiguity is surfaced, not hidden |
| G4 | Work everywhere on screen | Desktop app answers over browser, IDE, Office, PDF readers, images (OCR/vision) |
| G5 | Ask when unsure | Ambiguous marks trigger a "which one?" choice instead of a confident wrong answer |

## Current priorities (2026-09-23)

- **Accuracy + OS-level reach over local/privacy.** Cloud APIs are acceptable. Existing privacy tiers stay
  but get no new investment for now.
- Spatial is an **independent, standalone product**.
- **Jev (TypeSafe)** is used for System-One judgments (which object, ambiguous?, routing). **Laya** is evaluated
  on the same protocol and is the path to our own fine-tuned, free resolver later.

## In scope (next ~3 months)

- Core foundation: independence, shared `SpatialContext` contract, OCR candidates, opt-in trace log, eval harness.
- System-One resolver (Jev first, Laya second, deterministic fallback) + clarification UI.
- Windows UIA spike → Tauri desktop app (hotkey, freeze-frame overlay, UIA + OCR candidates, bundled server).

## Out of scope (for now)

- Acting on the screen (clicking, typing) — Spatial is read-only by design.
- Accounts, billing, teams, sharing, analytics, marketing site.
- Mobile.
- Linux desktop (after Windows + macOS).

## Success looks like

A user on Windows presses the hotkey over VS Code, a PDF, a chart in Excel or a web page, circles something,
asks "why?", and within ~2 s sees the right thing highlighted and a correct, short answer — or a quick
"did you mean A or B?" when it genuinely can't tell.
