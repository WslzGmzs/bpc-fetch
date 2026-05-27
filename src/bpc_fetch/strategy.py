"""HTTP bypass strategy: apply correct headers per site."""
import random
import httpx
from .sites import SiteStrategy

UA_GOOGLEBOT = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
UA_BINGBOT = "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)"
UA_FACEBOOKBOT = "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"
UA_NORMAL = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"

REFERER_GOOGLE = "https://www.google.com/"
REFERER_FACEBOOK = "https://www.facebook.com/"
REFERER_TWITTER = "https://t.co/"

TIMEOUT = 30.0


def build_headers(strategy: SiteStrategy) -> dict[str, str]:
    """Build HTTP headers based on the site's bypass strategy."""
    headers: dict[str, str] = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    ua = strategy.useragent.lower() if strategy.useragent else ""
    if ua == "googlebot":
        headers["User-Agent"] = UA_GOOGLEBOT
    elif ua == "bingbot":
        headers["User-Agent"] = UA_BINGBOT
    elif ua in ("facebookbot", "facebook"):
        headers["User-Agent"] = UA_FACEBOOKBOT
    else:
        headers["User-Agent"] = UA_NORMAL

    ref = strategy.referer.lower() if strategy.referer else ""
    if ref == "google":
        headers["Referer"] = REFERER_GOOGLE
    elif ref == "facebook":
        headers["Referer"] = REFERER_FACEBOOK
    elif ref == "twitter":
        headers["Referer"] = REFERER_TWITTER
    elif not ua:
        headers["Referer"] = REFERER_GOOGLE

    if strategy.random_ip:
        ip = f"{random.randint(1,223)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"
        headers["X-Forwarded-For"] = ip

    return headers


def build_fallback_headers() -> dict[str, str]:
    """Fallback: Googlebot UA + Google referer."""
    return {
        "User-Agent": UA_GOOGLEBOT,
        "Referer": REFERER_GOOGLE,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }


async def fetch_page(url: str, strategy: SiteStrategy | None = None, client: httpx.AsyncClient | None = None) -> tuple[str, int]:
    """Fetch page HTML with bypass headers. Returns (html, status_code)."""
    headers = build_headers(strategy) if strategy else build_fallback_headers()
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(follow_redirects=True, timeout=TIMEOUT)
    try:
        resp = await client.get(url, headers=headers)
        return resp.text, resp.status_code
    finally:
        if own_client:
            await client.aclose()


async def fetch_with_retries(url: str, strategy: SiteStrategy | None = None, client: httpx.AsyncClient | None = None) -> tuple[str, int]:
    """Try primary strategy, fallback to googlebot, then archive.org."""
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(follow_redirects=True, timeout=TIMEOUT)
    try:
        html, status = await fetch_page(url, strategy, client)
        if status == 200 and _has_content(html):
            return html, status

        # Try googlebot UA
        if not strategy or strategy.useragent != "googlebot":
            fallback = SiteStrategy(domain=(strategy.domain if strategy else ""), useragent="googlebot")
            html, status = await fetch_page(url, fallback, client)
            if status == 200 and _has_content(html):
                return html, status

        # Try archive.org Wayback Machine
        try:
            archive_url = f"https://web.archive.org/web/2/{url}"
            resp = await client.get(archive_url, headers={"User-Agent": UA_NORMAL}, follow_redirects=True)
            if resp.status_code == 200 and _has_content(resp.text):
                return resp.text, 200
        except Exception:
            pass

        return html, status
    finally:
        if own_client:
            await client.aclose()


def _has_content(html: str) -> bool:
    """Check if HTML has meaningful article content (not just a paywall/redirect)."""
    if len(html) < 500:
        return False
    lower = html.lower()
    if "<article" in lower or "articlebody" in lower or "article-body" in lower:
        return True
    if lower.count("<p") > 3:
        return True
    return len(html) > 5000
