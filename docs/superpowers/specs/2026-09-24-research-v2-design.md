# Research v2 (Tavily + Jev) and Answer Model — Design

**Date:** 2026-09-24
**Status:** Approved in chat 2026-09-24 ("we use tavily … lets move ahead")
**Inspired by:** `D:/PROJECTS/Cited Multi-Agent Researcher` (orchestrator → search agents → citation agent → synthesis → judge)

## Goal

Cited answers that are faster, better-sourced and verified: Tavily replaces Gemini/DuckDuckGo scraping as the
search layer, Jev ranks passages and checks citations, and the NVIDIA answer model becomes one that actually answers.

## Findings that shape it (2026-09-24 live probes)

- Configured `nvidia/nemotron-3.5-lightning-30b-a3b` never answers (3/3 timeouts). `nvidia/nemotron-3-super-120b-a12b`
  answers correctly in 1.5–4 s; free tier returns occasional 503s (1 in 4) on every working model.
- Tavily `search_depth="fast"` returns ranked content chunks per source (no page fetching needed). Keyless mode's
  monthly cap is already exhausted → the server needs `TAVILY_API_KEY`; DuckDuckGo stays as the no-key fallback.

## Design

### 1. Answer model

- Default `NVIDIA_MODEL` → `nvidia/nemotron-3-super-120b-a12b` (config default + `.env.example`). The user sets the same
  line in `server/.env`.
- `answer_stream`: when a provider fails **before producing any text** with HTTP 429/502/503/504 or a connect/timeout
  error, retry that same provider once after 0.5 s, then fall through as today.

### 2. Search layer (`research.py`)

| Mirrors | Spatial |
|---|---|
| SearchAgent (Gemini grounding) | `_tavily_search(query, k)`: `POST https://api.tavily.com/search`, `search_depth="fast"`, `chunks_per_source=3`, `max_results=k`; hits carry `passages` = Tavily chunks and `score`. Used when `TAVILY_API_KEY` is set. |
| — | Fallback: existing DuckDuckGo search + page fetch + passage selection (unchanged) when no key or Tavily fails. |
| — | **Gemini removed** (`_gemini_search`, `GOOGLE_API_KEY`, `GEMINI_MODEL`). |
| Orchestrator classify/decompose | **Jev `mode`** (already per ask). `compare` with marks of ≥ 2 roles → one query per role (source text, target text), searched in parallel; otherwise one query. |
| CitationAgent | `dedupe_and_score(hits)`: dedupe by host+path; `credibility` = .gov/.edu 0.95 · known reference/news hosts 0.85 · .org 0.75 · else 0.6; ids re-numbered 1..n after ranking. |

### 3. Passage ranking with Jev (E3)

One Jev request after search: state = question + marked text + passages `P1…Pn` (≤ 12, each ≤ 600 chars, scrubbed);
one Score question per passage ("How well does `passages.Pk` help answer `question` about `marked`?", 4 levels
from *irrelevant* to *directly answers it*). Keep passages with expected level ≥ 1.5 (of 0–3), best first, max 2 per
source, max 4 sources. Jev unavailable → keep Tavily/DDG order.

### 4. Citation check with Jev (JudgeAgent, live)

After the answer text is final and before `complete`: split the answer into sentences; for each sentence with
`[n]` refs, one Choice per (sentence, source) pair — `supports` / `partly` / `unrelated` / `contradicts` — over the
source's passages. Response gains `citation_checks: [{sentence_index, source_id, verdict, probability}]` and
`unsupported_citations: [source ids]` (verdict unrelated/contradicts with p ≥ 0.5). Skipped when no citations or
Jev unavailable. Extension marks those `[n]` with ⚠ in the sources list.

### 5. Settings

`TAVILY_API_KEY` (optional), `SPATIAL_RESEARCH_SEARCH=tavily|ddg|auto` (default `auto`: Tavily if key else DDG),
`SPATIAL_RESEARCH_VERIFY=on|off` (default on).

## Error handling

Every network step is best-effort and time-boxed (Tavily 6 s, Jev per existing 1.5 s budget); any failure degrades
to the previous step's output. An ask never fails because research, ranking or verification failed.

## Testing

- Tavily client with `httpx.MockTransport`: request shape (auth, depth, chunks), parsing, failure → DDG fallback.
- `dedupe_and_score`: dedupe, credibility, renumbering.
- Compare queries: two roles → two queries; one role → one.
- Jev passage ranking and citation check with fake `system_one.evaluate` (thresholds, caps, fallback order,
  scrubbing, unsupported ids).
- Provider retry: 503 then success → one answer; 503 twice → fall through; failure after text → no retry.
- Live smoke (manual, needs keys): one research ask end-to-end; record sources, latency and checks in MEMORY.

## Non-goals

Tavily `research()` endpoint (30–120 s, too slow per ask); multi-hop agent loops; UI redesign beyond the ⚠ marker.
