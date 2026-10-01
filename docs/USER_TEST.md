# Small user test (8-10 people)

Goal: find out whether the beachhead (Windows users who read dense interfaces all day: analysts, finance/ops, researchers,
students working with PDFs and dashboards) gets value quickly, comes back, and would be unhappy to lose it. This is a
learning exercise, not a launch. Nothing here needs telemetry; everything is observed or self-reported.

## Who and how many

- 8-10 people, all Windows 10/11, all already use an AI assistant weekly. Mix: ~5 analysts/ops/finance, ~3 researchers/students,
  1-2 from support/QA (to test the secondary use case).
- Recruit from people you can reach directly; offer a 30-minute session. Do not recruit from people who will be polite.

## Before each session (you)

1. Send the installer. Until it is signed (`docs/SIGNING.md`), tell them the exact SmartScreen steps: **More info → Run anyway**.
   Say plainly that the build is unsigned and why.
2. Decide the key: they use **their own** API key (best signal, no cost to you) or a temporary key you revoke after the session.
   Never paste keys into chat or email; they type it into Settings → API keys themselves.
3. Consent, in writing, in two sentences: what the app does with their screen (marked text/crop + question go to the answer
   provider they configure; password-manager windows are never read), and that you will take notes but will **not** record
   their screen or collect screen content. Let them hide anything private before starting.

## Session script (30 min, they share their screen)

Give tasks as goals, not instructions. Do not explain the UI; write down every hesitation.

| # | Task (say this) | What you watch |
|---|---|---|
| 1 | "Get this set up so it can answer a question." | Can they find Settings → API keys unaided? Time to first configured provider. |
| 2 | "Open something you actually work with (a PDF, a dashboard, a spreadsheet) and ask about one specific thing in it using the app." | Time to first answer; did the **right** element get answered (mark it right/wrong); did a "Did you mean" clarification appear; did they re-mark. |
| 3 | "Dictate a short note into any text field." | Do they find Alt+Shift+D; does the text land; do they trust it. |
| 4 | "Find that note again, then set yourself a reminder for 10 minutes from now." | Do they discover recall (Alt+Shift+H) and the dashboard; does the reminder popup surprise them. |
| 5 | "Tell me where your data went during this session." | Do they understand what is local and what left the machine. |

## What to record per person (a one-line row)

`participant | task 1 minutes | task 2 minutes | answer correct? (y/n) | clarifications | confusions (short) | would they keep it? (y/n)`

Ask them to press **Copy diagnostics** on the Home page and paste it to you at the end: it contains only service status and
event categories (no prompts, answers or screen content).

## Five questions at the end

1. "How would you feel if you could no longer use this?" — very disappointed / somewhat / not disappointed. (the key number)
2. "What is the main thing you would use it for?" (their words, verbatim)
3. "What nearly stopped you today?" (setup, trust, wrong answer, speed)
4. "How often would you realistically use it?" — daily / weekly / monthly / never.
5. "What would you pay per month for it, if anything?" (a number, or "nothing")

## What counts as success (decide before you start)

| Signal | Threshold to keep going on this direction |
|---|---|
| Got a correct answer to a real question within 3 minutes, unaided | at least 7 of 10 |
| Answer was about the thing they meant (task 2 correct) | at least 85% of asks across all participants |
| "Very disappointed" if lost | at least 4 of 10 (about 40%) |
| Would use at least weekly | at least 5 of 10 |
| Would pay something | at least 3 of 10 name a number above zero |

Below the thresholds is useful: read the "what nearly stopped you" answers and fix the top two before the next round.

## After the round

- Write the table and the verbatim quotes into `docs/MEMORY.md` under a dated heading; keep names out of the repo.
- Decide: double down on personal desktop use, move toward the support/QA workflow, or fix trust/setup first. Use the
  secondary signals: which participants asked for team features, and what the support/QA people did differently.
- Rotate or revoke every temporary key you handed out.
