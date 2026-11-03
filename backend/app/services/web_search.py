"""Web search tool for the LLM. Results are untrusted and treated as data by the prompt."""
import asyncio

RETRY_DELAYS_SECONDS = [3, 8]  # DuckDuckGo often refuses rapid queries, then recovers.


def _search(query: str, max_results: int) -> list[dict]:
    from ddgs import DDGS

    return [
        {"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")}
        for r in DDGS(timeout=10).text(query, max_results=max_results)
    ]


async def web_search(query: str, max_results: int = 5) -> list[dict]:
    for delay in RETRY_DELAYS_SECONDS:
        try:
            return await asyncio.to_thread(_search, query, max_results)
        except Exception:  # ddgs raises several unrelated types, all worth one more try
            await asyncio.sleep(delay)
    return await asyncio.to_thread(_search, query, max_results)
