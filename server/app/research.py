"""Research mode: ground the answer in a handful of web sources so it is precise and cited.

Pipeline (no API key needed): question + marked text -> DuckDuckGo HTML search -> fetch top pages ->
pick the few passages that overlap the question -> hand them to the provider chain as numbered sources.
Optional: when GOOGLE_API_KEY is set and `google-generativeai` is installed, Gemini grounding adds
its sources too (pattern from D:/PROJECTS/Cited Multi-Agent Researcher). Every network step is
best-effort and time-boxed; with zero sources the normal (uncited) answer path still runs.
"""

from __future__ import annotations

import html
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PointAndAsk/0.2 (+research mode)"
STOP = set(
    "the a an of to in on for and or is are was were be this that it its as by with from at what why how does do which who when where into than then so if not can".split()
)
SEARCH_TIMEOUT = 6.0
FETCH_TIMEOUT = 6.0
MAX_PAGE_CHARS = 40_000
BLOCKED_HOSTS = (
    "facebook.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "pinterest.",
    "tiktok.com",
    "youtube.com",
)

RESEARCH_SYSTEM = (
    "You are a precise tutor. The user circled a region of what they are reading and asked about it. "
    "Answer using ONLY the marked text and the numbered sources. At most three short sentences, no preamble, "
    "no filler, no restating the question. Put the source number like [1] after each claim it supports. "
    "Only when no source supports an answer, start with 'Not settled by sources:' and give the most likely "
    "answer from the marked text; otherwise never write that phrase. Never invent citations."
)


def _terms(text: str) -> set[str]:
    return {
        t for t in re.findall(r"[a-z0-9][a-z0-9\-']{1,}", text.lower()) if t not in STOP
    }


def build_query(question: str, anchors: list[dict[str, Any]]) -> str:
    """Question plus the first few words of the strongest anchor so the search is about *this* text."""
    anchor = next((str(a.get("text", "")) for a in anchors if a.get("text")), "")
    anchor_words = " ".join(anchor.split()[:8])
    return f"{question.strip()} {anchor_words}".strip()[:200]


def _ddg_search(query: str, k: int) -> list[dict[str, str]]:
    url = "https://html.duckduckgo.com/html/"
    try:
        with httpx.Client(
            timeout=SEARCH_TIMEOUT,
            headers={"User-Agent": UA},
            follow_redirects=True,
            trust_env=False,
        ) as client:
            response = client.post(url, data={"q": query, "kl": "us-en"})
            response.raise_for_status()
    except Exception:
        return []
    results: list[dict[str, str]] = []
    for block in re.findall(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>(.*?)(?=<a[^>]+class="result__a"|$)',
        response.text,
        re.S,
    ):
        href, title_html, rest = block
        target = href
        if "duckduckgo.com/l/" in href or href.startswith("/l/"):
            target = unquote(parse_qs(urlparse(href).query).get("uddg", [""])[0])
        if not target.startswith("http"):
            continue
        host = urlparse(target).netloc.lower()
        if any(b in host for b in BLOCKED_HOSTS):
            continue
        snippet = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', rest, re.S)
        results.append(
            {
                "url": target,
                "title": _clean(title_html)[:160],
                "snippet": _clean(snippet.group(1))[:300] if snippet else "",
            }
        )
        if len(results) >= k:
            break
    return results


def _gemini_search(query: str, k: int) -> list[dict[str, str]]:
    """Gemini grounding (optional). Returns the grounding chunks as sources, like the Cited Researcher's SearchAgent."""
    key = os.getenv("GOOGLE_API_KEY", "")
    if not key:
        return []
    try:
        import google.generativeai as genai  # type: ignore
    except Exception:
        return []
    try:
        genai.configure(api_key=key)
        tool = genai.protos.Tool(google_search=genai.protos.Tool.GoogleSearch())
        model = genai.GenerativeModel(
            model_name=os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite"), tools=[tool]
        )
        response = model.generate_content(
            f"Find the most authoritative sources for: {query}",
            request_options={"timeout": SEARCH_TIMEOUT * 2},
        )
        chunks = response.candidates[0].grounding_metadata.grounding_chunks or []
        out = []
        for chunk in chunks:
            if getattr(chunk, "web", None) and chunk.web.uri:
                out.append(
                    {
                        "url": chunk.web.uri,
                        "title": chunk.web.title or chunk.web.uri,
                        "snippet": (response.text or "")[:300],
                    }
                )
            if len(out) >= k:
                break
        return out
    except Exception:
        return []


def _clean(fragment: str) -> str:
    text = re.sub(
        r"<script.*?</script>|<style.*?</style>|<noscript.*?</noscript>",
        " ",
        fragment,
        flags=re.S | re.I,
    )
    text = re.sub(r"<br\s*/?>|</p>|</div>|</li>|</h\d>|</tr>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n", text).strip()


def fetch_text(url: str) -> str:
    try:
        with httpx.Client(
            timeout=FETCH_TIMEOUT,
            headers={"User-Agent": UA, "Accept": "text/html,*/*"},
            follow_redirects=True,
            trust_env=False,
        ) as client:
            response = client.get(url)
            if "html" not in response.headers.get(
                "content-type", ""
            ) and not response.text.lstrip().startswith("<"):
                return ""
            return _clean(response.text[: MAX_PAGE_CHARS * 4])[:MAX_PAGE_CHARS]
    except Exception:
        return ""


def select_passages(
    text: str, question: str, extra: str = "", n: int = 3, width: int = 420
) -> list[str]:
    """Paragraphs/sentence windows ranked by overlap with the question (and marked text) terms."""
    want = _terms(question) | _terms(extra)
    if not want or not text:
        return []
    units = [
        u.strip()
        for u in re.split(r"\n+|(?<=[.!?])\s+(?=[A-Z(])", text)
        if len(u.strip()) > 40
    ]
    scored = []
    for index, unit in enumerate(units):
        have = _terms(unit)
        overlap = len(want & have)
        if overlap == 0:
            continue
        scored.append((overlap / (1 + len(unit) / 600), index))
    scored.sort(reverse=True)
    passages, used = [], set()
    for _, index in scored:
        if index in used:
            continue
        window = " ".join(units[index : index + 2])[:width]
        used.update({index, index + 1})
        passages.append(window)
        if len(passages) >= n:
            break
    return passages


def gather(
    question: str, anchors: list[dict[str, Any]], max_sources: int = 4
) -> list[dict[str, Any]]:
    """Search + fetch + select, in parallel; returns [{id, url, title, passages}] with 1-based ids."""
    query = build_query(question, anchors)
    hits = _gemini_search(query, max_sources) + _ddg_search(query, max_sources * 2)
    seen, unique = set(), []
    for hit in hits:
        key = urlparse(hit["url"]).netloc.lower() + urlparse(hit["url"]).path.rstrip(
            "/"
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(hit)
    marked = " ".join(str(a.get("text", "")) for a in anchors[:3])
    sources: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for hit, text in zip(
            unique, pool.map(lambda h: fetch_text(h["url"]), unique[: max_sources * 2])
        ):
            passages = select_passages(text, question, marked) if text else []
            if not passages and hit.get("snippet"):
                passages = [hit["snippet"]]
            if not passages:
                continue
            sources.append(
                {
                    "id": len(sources) + 1,
                    "url": hit["url"],
                    "title": hit["title"] or hit["url"],
                    "passages": passages,
                }
            )
            if len(sources) >= max_sources:
                break
    return sources


def sources_block(sources: list[dict[str, Any]]) -> str:
    lines = ["Sources (cite by number):"]
    for source in sources:
        lines.append(f"[{source['id']}] {source['title']} — {source['url']}")
        lines += [f"    {p}" for p in source["passages"]]
    return "\n".join(lines)


def cited_ids(answer: str, sources: list[dict[str, Any]]) -> list[int]:
    valid = {s["id"] for s in sources}
    return sorted(
        {int(n) for n in re.findall(r"\[(\d{1,2})\]", answer) if int(n) in valid}
    )
