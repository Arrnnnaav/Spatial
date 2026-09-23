# Providers

All providers are configured by environment variables in `server/.env` (see `.env.example`).
`SPATIAL_PROVIDERS` sets the order; the first configured provider that responds wins.
Each provider has a text `*_MODEL` and an optional `*_VISION_MODEL`. When the request has a crop:

- provider has a vision model → the crop is sent as an image;
- provider has no vision model (or the vision call fails, e.g. model not pulled) → the crop is OCR'd
  with RapidOCR (CPU) and the text is added to the prompt; the text model answers.

| Provider | Kind | Base URL | Free? | Suggested text / vision models |
|---|---|---|---|---|
| `ollama` | native `/api/chat` | `http://127.0.0.1:11434` | yes, local | `qwen3:4b-instruct` / `qwen2.5vl:3b` (3.2 GB, fits 4 GB VRAM), `gemma3:4b`, `moondream` (1.7 GB, weaker) |
| `openrouter` | OpenAI-compatible | `https://openrouter.ai/api/v1` | free tier (`:free` models, rate-limited) | `qwen/qwen3-4b:free` / `qwen/qwen2.5-vl-72b-instruct:free`, `google/gemma-3-12b-it:free` (vision) |
| `nvidia` | OpenAI-compatible | `https://integrate.api.nvidia.com/v1` | free credits on signup | `openai/gpt-oss-20b` / `meta/llama-3.2-11b-vision-instruct` |
| `openai` | OpenAI | `https://api.openai.com/v1` | no | `gpt-4o-mini` (vision) |
| `anthropic` | Messages API | `https://api.anthropic.com/v1` | no | `claude-sonnet-5` (vision) |

Model names on OpenRouter / NVIDIA change over time; check https://openrouter.ai/models?q=free and
https://build.nvidia.com/models and override with `OPENROUTER_MODEL`, `OPENROUTER_VISION_MODEL`,
`NVIDIA_MODEL`, `NVIDIA_VISION_MODEL`.

Any other OpenAI-compatible gateway (Groq, Together, LM Studio, llama.cpp server, vLLM) works by pointing
`OPENAI_BASE_URL` + `OPENAI_API_KEY` + `OPENAI_MODEL` at it.

## NVIDIA NIM free tier — verified

With a `nvapi-…` key from https://build.nvidia.com, `GET https://integrate.api.nvidia.com/v1/models` lists
~80 models, but a fresh free account can only *call* a subset — the rest return `404 Function not found for
account` or `410 Gone` (retired). Probed on 2026-09-16, these answered:

| Model | Type | Notes |
|---|---|---|
| `openai/gpt-oss-20b` | text | clean answers, ~10 s — **default** |
| `nvidia/nemotron-3-super-120b-a12b` | text | strong, slower |
| `nvidia/nemotron-3-super-120b-a12b` | text | **default (2026-09-24)**: reasons then answers correctly in ~2–4 s; free tier returns occasional 503s (retried once) |
| `nvidia/nemotron-3.5-lightning-30b-a3b` | text | times out for this account (2026-09-24) — do not use |
| `z-ai/glm-5.3` | text | |
| `meta/llama-3.2-11b-vision-instruct` | vision | sees the crop, ~8–15 s — **default vision** |
| `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` | vision + reasoning | |

Retired: `meta/llama-3.1-8b-instruct`, `meta/llama-3.3-70b-instruct`, `meta/llama-3.2-3b-instruct` (410).
To re-probe with your key: `python scripts/try_providers.py --direct`, or the loop in `scripts/probe_nvidia.py`.
Keep the key in `server/.env` only (gitignored).

## Forcing a provider per ask

The extension popup lists the providers the server reports as configured; choosing one sends
`provider: "<name>"` with the ask, which bypasses the order (no fallback to others).

## Observability

Every `/api/ask` response carries `provider`, `model`, `vision`, `ocr`, `status` (`generated` | `fallback`),
`note` and an `errors` map of what each earlier provider said, so a wrong key or an unpulled model is
visible in the answer footer of the extension panel.
