"""Retrieval: hidden JSON APIs first (httpx, cheap and fast); fall back to a
real browser (Playwright) when the site only renders client-side.
"""

import asyncio
from typing import Any

import httpx


async def fetch_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    """GET a hidden/undocumented JSON API and return parsed json."""
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()


def fetch_rendered_html(url: str, *, wait_selector: str = "body") -> str:
    """Render a page in headless Chromium (needs `playwright install chromium`)
    and return the final HTML, for scraping after JS has run.
    """
    from playwright.sync_api import sync_playwright  # lazy: heavy startup

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_selector(wait_selector)
            return page.content()
        finally:
            browser.close()


async def fetch_json_many(urls: list[str], **kwargs: Any) -> list[Any]:
    """Concurrently fetch several JSON endpoints (per-store scrapes)."""
    return await asyncio.gather(*(fetch_json(u, **kwargs) for u in urls))
