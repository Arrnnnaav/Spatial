"""Research mode: ground the answer in a handful of web sources so it is precise and cited.

Pipeline (after D:/PROJECTS/Cited Multi-Agent Researcher: search agents -> citation agent -> synthesis -> judge):
question + marked text -> one query (or one per mark for a source/target comparison) -> Tavily search
(`search_depth="fast"`, ranked chunks per source; needs TAVILY_API_KEY) or, without a key, DuckDuckGo HTML search +
page fetch + passage selection -> dedupe + credibility score -> Jev passage ranking (app/semantic.py) -> numbered
sources for the provider chain. Every network step is best-effort and time-boxed; with zero sources the normal
(uncited) answer path still runs.
"""

from __future__ import annotations

import html
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from app import semantic
from app.config import settings

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PointAndAsk/0.2 (+research mode)"
STOP = set(
    "the a an of to in on for and or is are was were be this that it its as by with from at what why how does do which who when where into than then so if not can".split()
)
SEARCH_TIMEOUT = 6.0
TAVILY_URL = "https://api.tavily.com/search"
_tavily_transport: httpx.BaseTransport | None = None  # tests inject httpx.MockTransport
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


def build_queries(question: str, anchors: list[dict[str, Any]], mode: str | None = None) -> list[str]:
    """One query per mark role for a comparison (search both sides in parallel), else one query."""
    roles: dict[str, list[dict[str, Any]]] = {}
    for anchor in anchors:
        roles.setdefault(str(anchor.get("role") or "reference"), []).append(anchor)
    if mode == "compare" and len(roles) >= 2:
        return [build_query(question, group) for group in roles.values()][:3]
    return [build_query(question, anchors)]


def _tavily_search(query: str, k: int) -> list[dict[str, Any]]:
    """Tavily search tuned for per-ask latency: `fast` depth returns ranked content chunks, so no page fetching."""
    key = settings.tavily_api_key
    if not key:
        return []
    body = {"query": query[:400], "search_depth": "fast", "chunks_per_source": 3, "max_results": k,
            "include_answer": False}
    try:
        with httpx.Client(timeout=SEARCH_TIMEOUT, transport=_tavily_transport, trust_env=False) as client:
            response = client.post(TAVILY_URL, json=body, headers={"Authorization": f"Bearer {key}"})
            response.raise_for_status()
            results = response.json().get("results") or []
    except Exception:
        return []
    hits = []
    for item in results:
        if not isinstance(item, dict) or not str(item.get("url", "")).startswith("http"):
            continue
        host = urlparse(item["url"]).netloc.lower()
        if any(b in host for b in BLOCKED_HOSTS):
            continue
        chunks = [c.strip() for c in str(item.get("content") or "").split("[...]") if c.strip()]
        hits.append({"url": item["url"], "title": str(item.get("title") or item["url"])[:160],
                     "passages": [c[:600] for c in chunks][:3], "score": float(item.get("score") or 0.0)})
    return hits


REFERENCE_HOSTS = ("wikipedia.org", "britannica.com", "reuters.com", "bbc.com", "nature.com", "arxiv.org",
                   "nih.gov", "who.int", "docs.python.org", "developer.mozilla.org", "stackexchange.com",
                   "stackoverflow.com")


def credibility(url: str) -> float:
    """Citation-agent style source prior: official > reference/news > organisations > the rest."""
    host = urlparse(url).netloc.lower()
    if host.endswith(".gov") or ".gov." in host or host.endswith(".edu") or ".edu." in host:
        return 0.95
    if any(host == h or host.endswith("." + h) for h in REFERENCE_HOSTS):
        return 0.85
    if host.endswith(".org"):
        return 0.75
    return 0.6


def dedupe_and_score(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen, out = set(), []
    for hit in hits:
        parsed = urlparse(hit["url"])
        key = parsed.netloc.lower() + parsed.path.rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        out.append({**hit, "credibility": credibility(hit["url"])})
    return out


def rank_passages(question: str, marked: str, sources: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """Jev passage ranking (None when System One is unavailable: keep search order)."""
    return semantic.rank_passages(question, marked, sources)


def _ddg_sources(query: str, question: str, marked: str, k: int) -> list[dict[str, Any]]:
    hits = _ddg_search(query, k * 2)
    out = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for hit, text in zip(hits, pool.map(lambda h: fetch_text(h["url"]), hits)):
            passages = select_passages(text, question, marked) if text else []
            if not passages and hit.get("snippet"):
                passages = [hit["snippet"]]
            if passages:
                out.append({"url": hit["url"], "title": hit["title"] or hit["url"], "passages": passages, "score": 0.0})
    return out


def gather(question: str, anchors: list[dict[str, Any]], max_sources: int = 4,
           mode: str | None = None, use_system_one: bool = True) -> list[dict[str, Any]]:
    """Search (Tavily, else DuckDuckGo) per query in parallel -> dedupe + credibility -> Jev ranking -> numbered
    sources [{id, url, title, passages, credibility}]."""
    marked = " ".join(str(a.get("text", "")) for a in anchors[:3])
    queries = build_queries(question, anchors, mode)
    use_tavily = settings.research_search in {"auto", "tavily"} and bool(settings.tavily_api_key)

    def search(query: str) -> list[dict[str, Any]]:
        hits = _tavily_search(query, max_sources + 1) if use_tavily else []
        return hits or _ddg_sources(query, question, marked, max_sources)

    with ThreadPoolExecutor(max_workers=len(queries)) as pool:
        per_query = list(pool.map(search, queries))
    # Interleave per-query results so a comparison keeps sources from both sides.
    interleaved = [hit for group in zip_longest_nonnull(per_query) for hit in group]
    sources = dedupe_and_score(interleaved)
    ranked = rank_passages(question, marked, sources) if use_system_one else None
    if ranked is not None:
        sources = ranked
    sources = sources[:max_sources]
    return [{"id": index + 1, "url": s["url"], "title": s["title"], "passages": s["passages"],
             "credibility": s.get("credibility", credibility(s["url"]))} for index, s in enumerate(sources)]


def zip_longest_nonnull(groups: list[list[Any]]) -> list[list[Any]]:
    rows = []
    for index in range(max((len(g) for g in groups), default=0)):
        rows.append([g[index] for g in groups if index < len(g)])
    return rows


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
