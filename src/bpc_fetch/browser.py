"""Playwright-based browser fetch for block_js sites."""
import asyncio
import re
from contextlib import asynccontextmanager
from pathlib import Path

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from .sites import SiteStrategy

BROWSER_TIMEOUT = 30000


async def ensure_browser() -> dict:
    """Check if Playwright Chromium is installed. Returns status dict."""
    try:
        from playwright._impl._driver import compute_driver_executable
        driver = compute_driver_executable()
        return {"ok": True, "driver": str(driver)}
    except Exception:
        pass
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            version = browser.version
            await browser.close()
            return {"ok": True, "version": version}
    except Exception as e:
        return {"ok": False, "error": str(e), "install_cmd": "playwright install chromium"}


class BrowserPool:
    """Reusable browser context pool for batch operations."""

    def __init__(self, max_contexts: int = 3):
        self._pw = None
        self._browser: Browser | None = None
        self._max = max_contexts
        self._sem = asyncio.Semaphore(max_contexts)

    async def start(self):
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=True)

    async def stop(self):
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()

    @asynccontextmanager
    async def page(self):
        async with self._sem:
            ctx = await self._browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
            )
            pg = await ctx.new_page()
            try:
                yield pg
            finally:
                await pg.close()
                await ctx.close()

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *_):
        await self.stop()


def _build_route_patterns(strategy: SiteStrategy) -> list[str]:
    """Convert BPC block_regex to Playwright route glob patterns."""
    if not strategy.block_regex:
        return []
    regex_str = strategy.block_regex
    patterns = []
    for part in re.split(r'\|', regex_str):
        part = part.strip().strip("()")
        glob = _regex_to_glob(part)
        if glob:
            patterns.append(glob)
    if not patterns:
        patterns.append(f"**/*{strategy.domain}*paywall*")
    return patterns


def _regex_to_glob(regex_part: str) -> str:
    """Best-effort convert a simple regex fragment to a glob pattern."""
    s = regex_part.replace("\\.", ".").replace("\\/", "/")
    s = re.sub(r'\.\+', '*', s)
    s = re.sub(r'\.\*', '*', s)
    s = re.sub(r'\([^)]*\)', '*', s)
    s = re.sub(r'\[[^\]]*\]', '?', s)
    s = re.sub(r'[\\^$]', '', s)
    if not s or s == '*':
        return ""
    if not s.startswith("*"):
        s = "**/" + s
    if not s.endswith("*"):
        s = s + "*"
    return s


async def fetch_with_browser(
    url: str,
    strategy: SiteStrategy,
    pool: BrowserPool | None = None,
) -> tuple[str, int]:
    """Fetch page using Playwright, blocking paywall scripts via route."""
    own_pool = pool is None
    if own_pool:
        pool = BrowserPool(max_contexts=1)
        await pool.start()

    try:
        async with pool.page() as page:
            route_patterns = _build_route_patterns(strategy)
            for pattern in route_patterns:
                try:
                    await page.route(pattern, lambda route: route.abort())
                except Exception:
                    pass

            try:
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=BROWSER_TIMEOUT)
                status = resp.status if resp else 0
            except Exception:
                status = 0

            await page.wait_for_timeout(2000)

            html = await page.content()
            return html, status if status else 200
    finally:
        if own_pool:
            await pool.stop()

