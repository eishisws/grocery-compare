"""Maxi banner source — thin alias over the generic PCX engine."""

from __future__ import annotations

import contextlib

from price_getter.sources.pcx import (
    MAXI,
    PCXBanner,
    PCXBlockedError,
    extract_products_from_html,
    pcx_search,
    search_url,
)

__all__ = [
    "MAXI",
    "MaxiBlockedError",
    "PCXBanner",
    "PCXBlockedError",
    "extract_products_from_html",
    "pcx_search",
    "search_url",
]

MaxiBlockedError = PCXBlockedError  # legacy name kept for existing callers


@contextlib.contextmanager
def maxi_search(*, pause_seconds: float = 3.0):
    with pcx_search(MAXI, pause_seconds=pause_seconds) as fetch:
        yield fetch
