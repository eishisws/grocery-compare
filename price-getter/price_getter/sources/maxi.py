"""Maxi (Loblaws PC Express) product source.

Reverse-engineering notes, verified live 2026-10-28:

- Maxi's web app server-renders search results. Each search page's HTML
  embeds schema.org data inside
  `<script type="application/ld+json" data-next-head="">` tags — a
  ProductCollection with full product info (name, price, currency, sku,
  brand, image). No product XHR fires; the grid is in the document itself.
- Plain httpx GETs against www.maxi.ca are Akamai-blocked (403), so pages
  are fetched with Playwright Chromium in HEADED mode (headless Chromium
  gets "Access Denied"). In CI the nightly job runs under xvfb.
- The pcx-bff API accepts the app-level headers below with no Bearer
  token (e.g. pickup-locations returns 200). PCX storeId for "Maxi & Cie
  Hull du Plateau" is 7566. Database rows keep their own deterministic
  uuid5 ids — this source writes products only, never store rows.
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
import time
import urllib.parse
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

log = logging.getLogger(__name__)

# App-level identity shipped inside maxi.ca's public JS bundle (i.e. not a
# user secret) — copied from a DevTools capture of a real maxica session.
BFF_HEADERS: dict[str, str] = {
    "x-apikey": "C1xujSegT5j3ap3yexJjqhOfELwGKYvz",
    "site-banner": "maxi",
    "basesiteid": "maxi",
    "x-application-type": "web",
    "x-channel": "web",
    "x-loblaw-tenant-id": "ONLINE_GROCERIES",
    "business-user-agent": "PCXWEB",
    "Accept-Language": "fr",
    "Origin": "https://www.maxi.ca",
    "Referer": "https://www.maxi.ca/",
}

BASE = "https://www.maxi.ca"

_LD_SCRIPT = re.compile(
    r'<script type="application/ld\+json"[^>]*>(?P<json>.*?)</script>', re.DOTALL
)

# Akamai interstitial title when a request gets flagged
_BLOCKED_TITLE = "Access Denied"


class MaxiBlockedError(RuntimeError):
    """Akamai served the bot interstitial instead of search results."""


def search_url(query: str) -> str:
    """The SSR search page URL the maxi.ca SPA itself navigates to."""
    params = {"search-bar": query, "sort": "relevance"}
    return f"{BASE}/fr/search?{urllib.parse.urlencode(params)}"


def extract_products_from_html(html: str) -> list[dict[str, Any]]:
    """Pull products out of every JSON-LD block in a search page.

    Walks arbitrarily nested structures to find ProductCollections (top-level
    or under `mainEntity`), then flattens itemOffered entries to plain dicts.
    Items without a price are skipped (unavailable SKUs).
    """
    products: list[dict[str, Any]] = []
    seen: set[tuple[str, Any]] = set()

    for match in _LD_SCRIPT.finditer(html):
        try:
            data = json.loads(match.group("json"))
        except json.JSONDecodeError:
            continue

        for node in _walk(data):
            if not isinstance(node, dict) or node.get("@type") != "ProductCollection":
                continue
            items = ((node.get("offers") or {}).get("itemOffered")) or []
            for item in items:
                if not isinstance(item, dict) or item.get("@type") != "Product":
                    continue
                offers = item.get("offers") or {}
                price = offers.get("price")
                if price is None:
                    continue
                name = " ".join(str(item.get("name") or "").split())
                dedupe = (name, price)
                if not name or dedupe in seen:
                    continue
                seen.add(dedupe)
                products.append(
                    {
                        "name": name,
                        "price": Decimal(str(price)),
                        "currency": offers.get("priceCurrency") or "CAD",
                        "brand": _brand_name(item.get("brand")),
                        "image": item.get("image"),
                        "url": item.get("url"),
                    }
                )
    return products


def _walk(node: Any) -> Iterator[Any]:
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def _brand_name(brand: Any) -> str | None:
    if isinstance(brand, dict):
        return brand.get("name")
    if isinstance(brand, str):
        return brand
    return None


@contextlib.contextmanager
def maxi_search(*, pause_seconds: float = 3.0) -> Iterator[Any]:
    """Yield `fetch(query) -> list[product dict]` backed by a real browser.

    Headed Chromium is required: Akamai serves "Access Denied" to headless
    (also to plain httpx). One browser/page is reused for the whole run and
    navigations are paced to keep each page load looking like light browsing.
    """

    from playwright.sync_api import sync_playwright  # lazy: heavy startup

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        try:
            page = browser.new_context(locale="fr-CA").new_page()

            def fetch(query: str, *, max_wait_seconds: float = 15.0) -> list[dict[str, Any]]:
                log.info("maxi: fetching search page for %r", query)
                page.goto(search_url(query), wait_until="domcontentloaded", timeout=45_000)
                deadline = time.monotonic() + max_wait_seconds
                while time.monotonic() < deadline:
                    if _BLOCKED_TITLE in page.title():
                        raise MaxiBlockedError(
                            "Akamai served Access Denied instead of search results"
                        )
                    html = page.content()
                    products = extract_products_from_html(html)
                    if products:
                        time.sleep(pause_seconds)  # pace the next navigation
                        return products
                    time.sleep(1.0)  # SSR text arrives with the document; hydrates shortly
                html = page.content()
                products = extract_products_from_html(html)
                if not products:
                    raise MaxiBlockedError(
                        f"no products parsed for {query!r} (title={page.title()!r})"
                    )
                return products

            yield fetch
        finally:
            browser.close()
