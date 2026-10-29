"""Loblaws PC Express product sources: one engine, several banners.

Reverse-engineering notes, verified live 2026-10-28:

- Banner sites under the PCX/Iceberg platform (maxi.ca, provigo.ca,
  realcanadiansuperstore.ca, nofrills.ca, ...) server-render search results.
  Each search page's HTML embeds schema.org data inside
  `<script type="application/ld+json" data-next-head="">` — a
  ProductCollection with full product info (name, price, currency, sku,
  brand, image). No product XHR fires; the grid is in the document itself.
- Plain httpx GETs against those sites are Akamai-blocked (403), so pages
  are fetched with a real (headed) site: Playwright persistent profile
  (cookies survive across nightly runs, so the scraper reads as a returning
  visitor), the user's installed Edge on Windows, and automation flags
  suppressed. Headless Chromium gets "Access Denied" immediately. In CI the
  nightly job runs under xvfb. Be POLITE: one browser per run at a measured
  pace does not trip the shared platform flag; a dozen rapid launches in an
  hour does (we verified the hard way), and a live IP flag needs 24-48 h
  to expire - do not retry in a loop.
- The pcx-bff API (api.pcexpress.ca) accepts the app-level headers below
  with no Bearer token; `Origin` must match an allow-listed banner domain.
  PCX storeIds are Loblaws' legacy numbering — database rows keep their own
  deterministic uuid5 ids; this source writes products only, never stores.
"""

from __future__ import annotations

import contextlib
import json
import logging
import pathlib
import re
import sys
import time
import urllib.parse
from collections.abc import Iterator
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

log = logging.getLogger(__name__)

# App-level identity shipped inside the banners' public JS bundle (i.e. not a
# user secret) — copied from a DevTools capture of a real maxi.ca session.
_APIKEY = "C1xujSegT5j3ap3yexJjqhOfELwGKYvz"

_LD_SCRIPT = re.compile(
    r'<script type="application/ld\+json"[^>]*>(?P<json>.*?)</script>', re.DOTALL
)

# Akamai interstitial title when a request gets flagged
_BLOCKED_TITLE = "Access Denied"


@dataclass(frozen=True)
class PCXBanner:
    """One Loblaws-family banner (a store chain) on the Iceberg platform."""

    key: str  # pcx banner id, e.g. 'maxi' / 'superstore'
    host: str  # the marketing + shop domain, e.g. 'www.maxi.ca'
    search_path: str  # '/fr/search' or '/en/search'
    language: str  # Accept-Language for the site
    playwright_locale: str  # browser context locale, e.g. 'fr-CA'
    accept: str = field(default="application/json, text/plain, */*")

    def headers(self) -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"
            ),
            "Accept": self.accept,
            "x-apikey": _APIKEY,
            "site-banner": self.key,
            "basesiteid": self.key,
            "x-application-type": "web",
            "x-channel": "web",
            "x-loblaw-tenant-id": "ONLINE_GROCERIES",
            "business-user-agent": "PCXWEB",
            "Content-Type": "application/json",
            "Accept-Language": self.language,
            "Origin": f"https://{self.host}",
            "Referer": f"https://{self.host}/",
        }


MAXI = PCXBanner(
    key="maxi",
    host="www.maxi.ca",
    search_path="/fr/search",
    language="fr",
    playwright_locale="fr-CA",
)

# Real Canadian Superstore (Ottawa-area PCX stores: 1009 Richmond Rd, 1071
# Innes Rd, 2813 Eagleson Rd Kanata). Note: superstore.ca is NOT a valid
# BFF origin — the allow-listed host is realcanadiansuperstore.ca.
SUPERSTORE = PCXBanner(
    key="superstore",
    host="www.realcanadiansuperstore.ca",
    search_path="/en/search",
    language="en",
    playwright_locale="en-CA",
)


class PCXBlockedError(RuntimeError):
    """Akamai served the bot interstitial instead of search results."""


def search_url(banner: PCXBanner, query: str) -> str:
    """The SSR search page URL the banner's SPA itself navigates to."""
    params = {"search-bar": query, "sort": "relevance"}
    return f"https://{banner.host}{banner.search_path}?{urllib.parse.urlencode(params)}"


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


# Persistent browser profile on the user's real machine: cookies (including
# Akamai's _abck/_bm_sv sensor cookies) survive between runs, so the nightly
# scrape looks like a RETURNING visitor instead of a fresh anonymous browser.
# LocalAutomation fingerprints are suppressed too: real Edge channel on
# Windows, navigator.webdriver removed, and no `--enable-automation` flag.
_PROFILE_DIR = pathlib.Path.home() / ".grocery-compare" / "browser-profile"


def _launch_context(p, banner: PCXBanner):
    _PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    kwargs: dict[str, Any] = {
        "headless": False,
        "locale": banner.playwright_locale,
        "args": ["--disable-blink-features=AutomationControlled"],
        "ignore_default_args": ["--enable-automation"],
    }
    if sys.platform == "win32":
        # The user's actual installed Edge — closer to a real visitor than the
        # bundled Playwright Chromium (which ships a distinguishable build).
        kwargs["channel"] = "msedge"
    return p.chromium.launch_persistent_context(str(_PROFILE_DIR), **kwargs)


@contextlib.contextmanager
def pcx_search(banner: PCXBanner, *, pause_seconds: float = 3.0) -> Iterator[Any]:
    """Yield `fetch(query) -> list[product dict]` backed by a real browser.

    Headed Chromium is required: Akamai serves "Access Denied" to headless
    (also to plain httpx). One browser/page per call site, paced so the run
    looks like light browsing.
    """

    from playwright.sync_api import sync_playwright  # lazy: heavy startup

    with sync_playwright() as p:
        context = _launch_context(p, banner)
        try:
            page = context.new_page()

            def fetch(query: str, *, max_wait_seconds: float = 15.0) -> list[dict[str, Any]]:
                log.info("pcx[%s]: fetching search page for %r", banner.key, query)
                page.goto(search_url(banner, query), wait_until="domcontentloaded", timeout=45_000)
                deadline = time.monotonic() + max_wait_seconds
                while time.monotonic() < deadline:
                    if _BLOCKED_TITLE in page.title():
                        raise PCXBlockedError(
                            "Akamai served Access Denied instead of search results"
                        )
                    html = page.content()
                    products = extract_products_from_html(html)
                    if products:
                        time.sleep(pause_seconds)  # pace the next navigation
                        return products
                    time.sleep(1.0)  # SSR text arrives with the document; hydrates shortly
                products = extract_products_from_html(page.content())
                if not products:
                    raise PCXBlockedError(
                        f"no products parsed for {query!r} (title={page.title()!r})"
                    )
                return products

            yield fetch
        finally:
            context.close()
