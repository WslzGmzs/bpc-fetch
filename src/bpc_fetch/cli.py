"""CLI entrypoint for bpc-fetch."""
import argparse
import asyncio
import json
import sys
from pathlib import Path

from .sites import get_sites_map, domain_from_url, SITES_JS_DEFAULT


def main():
    parser = argparse.ArgumentParser(prog="bpc-fetch", description="Bypass paywall: search and fetch articles")
    parser.add_argument("--compact", action="store_true", help="Minimal JSON output")
    parser.add_argument("--sites-js", type=Path, default=None, help="Path to BPC sites.js")
    sub = parser.add_subparsers(dest="command")
    # Add --compact to all subcommands for flexible positioning
    _common = argparse.ArgumentParser(add_help=False)
    _common.add_argument("--compact", action="store_true")
    _common.add_argument("--sites-js", type=Path, default=None)

    # doctor
    sub.add_parser("doctor", help="Verify setup and data files", parents=[_common])

    # sites
    p_sites = sub.add_parser("sites", help="List supported sites", parents=[_common])
    p_sites.add_argument("--filter", type=str, default="", help="Filter by domain substring")
    p_sites.add_argument("--strategy", type=str, default="", help="Filter by strategy type")
    p_sites.add_argument("--limit", type=int, default=50)

    # search
    p_search = sub.add_parser("search", help="Google search filtered to supported sites", parents=[_common])
    p_search.add_argument("query", nargs="+", help="Search query")
    p_search.add_argument("--site", type=str, default=None, help="Limit to specific domain")
    p_search.add_argument("--limit", type=int, default=20)

    # fetch
    p_fetch = sub.add_parser("fetch", help="Fetch article as markdown", parents=[_common])
    p_fetch.add_argument("url", help="Article URL")
    p_fetch.add_argument("--out-dir", type=Path, default=Path("."))
    p_fetch.add_argument("--no-images", action="store_true")

    # batch
    p_batch = sub.add_parser("batch", help="Batch fetch multiple URLs", parents=[_common])
    p_batch.add_argument("urls", nargs="*", help="URLs to fetch")
    p_batch.add_argument("--file", type=Path, default=None, help="File with URLs (one per line)")
    p_batch.add_argument("--out-dir", type=Path, default=Path("./articles"))
    p_batch.add_argument("--no-images", action="store_true")
    p_batch.add_argument("--concurrency", type=int, default=5)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        result = asyncio.run(_dispatch(args))
        print(json.dumps(result, ensure_ascii=False, indent=None if args.compact else 2))
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        sys.exit(1)


async def _dispatch(args) -> dict:
    if args.command == "doctor":
        return _cmd_doctor(args)
    if args.command == "sites":
        return _cmd_sites(args)
    if args.command == "search":
        return await _cmd_search(args)
    if args.command == "fetch":
        return await _cmd_fetch(args)
    if args.command == "batch":
        return await _cmd_batch(args)
    return {"ok": False, "error": f"unknown command: {args.command}"}


def _cmd_doctor(args) -> dict:
    issues = []
    js_path = args.sites_js or SITES_JS_DEFAULT
    if not js_path.exists():
        issues.append(f"sites.js not found at {js_path}")
    else:
        sites = get_sites_map(js_path)
        site_count = len(sites)

    try:
        import trafilatura
        traf_ok = True
    except ImportError:
        traf_ok = False
        issues.append("trafilatura not installed")

    try:
        import httpx
        httpx_ok = True
    except ImportError:
        httpx_ok = False
        issues.append("httpx not installed")

    return {
        "ok": len(issues) == 0,
        "sites_js": str(js_path),
        "sites_js_exists": js_path.exists(),
        "site_count": site_count if js_path.exists() else 0,
        "trafilatura": traf_ok,
        "httpx": httpx_ok,
        "issues": issues,
    }


def _cmd_sites(args) -> dict:
    js_path = args.sites_js or SITES_JS_DEFAULT
    sites = get_sites_map(js_path)

    filtered = list(sites.values())
    if args.filter:
        filtered = [s for s in filtered if args.filter.lower() in s.domain.lower() or args.filter.lower() in s.name.lower()]
    if args.strategy:
        filtered = [s for s in filtered if args.strategy.lower() in s.bypass_type().lower()]

    filtered = filtered[:args.limit]
    return {
        "ok": True,
        "total": len(sites),
        "shown": len(filtered),
        "sites": [{"domain": s.domain, "name": s.name, "bypass": s.bypass_type()} for s in filtered],
    }


async def _cmd_search(args) -> dict:
    from .search import search_across_sites, search_sites

    js_path = args.sites_js or SITES_JS_DEFAULT
    sites = get_sites_map(js_path)
    supported = set(sites.keys())
    query = " ".join(args.query)

    if args.site:
        results = search_sites(query, supported, args.limit, site_filter=args.site)
    else:
        results = search_across_sites(query, supported, args.limit)

    return {
        "ok": True,
        "query": query,
        "count": len(results),
        "results": results,
    }


async def _cmd_fetch(args) -> dict:
    from .extract import extract_article, article_to_markdown, download_images
    from .strategy import fetch_with_retries

    js_path = args.sites_js or SITES_JS_DEFAULT
    sites = get_sites_map(js_path)
    domain = domain_from_url(args.url)
    strategy = sites.get(domain)

    html, status = await fetch_with_retries(args.url, strategy)
    if status != 200:
        return {"ok": False, "error": f"HTTP {status}", "url": args.url, "domain": domain}

    article = extract_article(html, args.url)
    if not article["text"]:
        return {"ok": False, "error": "extraction_failed", "url": args.url, "domain": domain}

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = _slugify(article["title"] or domain)
    images_dir = out_dir / slug / "images"

    saved_images: list[Path] = []
    if not args.no_images and article["images"]:
        saved_images = await download_images(article["images"], images_dir)

    md = article_to_markdown(article, images_dir="images")
    md_path = out_dir / slug / f"{slug}.md"
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(md, encoding="utf-8")

    return {
        "ok": True,
        "url": args.url,
        "domain": domain,
        "strategy": strategy.bypass_type() if strategy else "fallback",
        "title": article["title"],
        "path": str(md_path),
        "images": len(saved_images),
        "text_length": len(article["text"]),
    }


async def _cmd_batch(args) -> dict:
    import asyncio as aio
    from .extract import extract_article, article_to_markdown, download_images
    from .strategy import fetch_with_retries
    import httpx

    urls = list(args.urls)
    if args.file and args.file.exists():
        urls.extend(line.strip() for line in args.file.read_text().splitlines() if line.strip() and not line.startswith("#"))

    if not urls:
        return {"ok": False, "error": "no URLs provided"}

    js_path = args.sites_js or SITES_JS_DEFAULT
    sites = get_sites_map(js_path)
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    sem = aio.Semaphore(args.concurrency)
    results = []

    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        async def _fetch_one(url: str) -> dict:
            async with sem:
                domain = domain_from_url(url)
                strategy = sites.get(domain)
                try:
                    html, status = await fetch_with_retries(url, strategy, client)
                    if status != 200:
                        return {"ok": False, "url": url, "error": f"HTTP {status}"}
                    article = extract_article(html, url)
                    if not article["text"]:
                        return {"ok": False, "url": url, "error": "extraction_failed"}
                    slug = _slugify(article["title"] or domain)
                    images_dir = out_dir / slug / "images"
                    if not args.no_images and article["images"]:
                        await download_images(article["images"], images_dir, client=client)
                    md = article_to_markdown(article, images_dir="images")
                    md_path = out_dir / slug / f"{slug}.md"
                    md_path.parent.mkdir(parents=True, exist_ok=True)
                    md_path.write_text(md, encoding="utf-8")
                    return {"ok": True, "url": url, "title": article["title"], "path": str(md_path)}
                except Exception as e:
                    return {"ok": False, "url": url, "error": str(e)}

        tasks = [_fetch_one(u) for u in urls]
        results = await aio.gather(*tasks)

    success = sum(1 for r in results if r.get("ok"))
    return {
        "ok": True,
        "total": len(urls),
        "success": success,
        "failed": len(urls) - success,
        "results": list(results),
    }


def _slugify(text: str) -> str:
    import re
    text = re.sub(r'[^\w\s-]', '', text.lower())
    text = re.sub(r'[\s_]+', '-', text)
    return text[:80].strip('-') or "article"
