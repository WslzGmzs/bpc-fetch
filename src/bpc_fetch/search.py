"""Search for articles on BPC-supported sites."""
import os
from urllib.parse import urlparse

import httpx


def search_sites(
    query: str,
    supported_domains: set[str],
    limit: int = 20,
    site_filter: str | None = None,
) -> list[dict]:
    """Search and filter results to supported paywall sites.

    Uses Brave Search API if BRAVE_API_KEY is set, otherwise DDG.
    """
    brave_key = os.environ.get("BRAVE_API_KEY", "")
    if brave_key:
        return _brave_search(query, supported_domains, limit, site_filter, brave_key)
    return _ddg_search(query, supported_domains, limit, site_filter)


def _brave_search(
    query: str,
    supported_domains: set[str],
    limit: int,
    site_filter: str | None,
    api_key: str,
) -> list[dict]:
    """Search via Brave Search API (free tier: 2000/month)."""
    search_query = f"site:{site_filter} {query}" if site_filter else query
    results: list[dict] = []
    try:
        resp = httpx.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": search_query, "count": min(limit * 2, 20)},
            headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
            timeout=15.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            for item in data.get("web", {}).get("results", []):
                url = item.get("url", "")
                domain = _get_domain(url)
                if site_filter:
                    if domain == site_filter or domain.endswith(f".{site_filter}"):
                        results.append(_format_result(item, domain))
                elif domain in supported_domains:
                    results.append(_format_result(item, domain))
                if len(results) >= limit:
                    break
    except Exception:
        pass
    return results[:limit]


def _ddg_search(
    query: str,
    supported_domains: set[str],
    limit: int,
    site_filter: str | None,
) -> list[dict]:
    """Fallback: DuckDuckGo search."""
    search_query = f"site:{site_filter} {query}" if site_filter else query
    results: list[dict] = []
    try:
        import warnings
        warnings.filterwarnings("ignore")
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            for r in ddgs.text(search_query, max_results=min(limit * 3, 60)):
                url = r.get("href", "")
                domain = _get_domain(url)
                if site_filter:
                    if domain == site_filter or domain.endswith(f".{site_filter}"):
                        results.append({"title": r.get("title", ""), "url": url, "domain": domain, "snippet": r.get("body", "")})
                elif domain in supported_domains:
                    results.append({"title": r.get("title", ""), "url": url, "domain": domain, "snippet": r.get("body", "")})
                if len(results) >= limit:
                    break
    except Exception:
        pass
    return results[:limit]


def search_across_sites(
    query: str,
    supported_domains: set[str],
    limit: int = 20,
) -> list[dict]:
    """Search with optional fallback to site-specific queries."""
    results = search_sites(query, supported_domains, limit)
    if len(results) < limit:
        top_sites = ["nytimes.com", "washingtonpost.com", "ft.com", "economist.com",
                     "bloomberg.com", "wsj.com", "theatlantic.com", "newyorker.com",
                     "wired.com", "nature.com", "science.org", "foreignaffairs.com"]
        seen_urls = {r["url"] for r in results}
        for site in top_sites:
            if len(results) >= limit:
                break
            more = search_sites(query, supported_domains, 5, site_filter=site)
            for r in more:
                if r.get("url") and r["url"] not in seen_urls:
                    results.append(r)
                    seen_urls.add(r["url"])
    return results[:limit]


def _format_result(item: dict, domain: str) -> dict:
    return {
        "title": item.get("title", ""),
        "url": item.get("url", ""),
        "domain": domain,
        "snippet": item.get("description", ""),
    }


def _get_domain(url: str) -> str:
    host = urlparse(url).hostname or ""
    parts = host.split(".")
    if len(parts) > 2:
        cctlds = ("au", "uk", "br", "il", "za", "nz", "sg", "jp", "tw", "in",
                  "ar", "uy", "mx", "pe", "bo", "cl", "co", "ke")
        if parts[-1] in cctlds:
            return ".".join(parts[-3:])
        return ".".join(parts[-2:])
    return host
