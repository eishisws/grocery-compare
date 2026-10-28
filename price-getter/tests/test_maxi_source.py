"""Offline tests for the PCX JSON-LD extraction (no browser, no network)."""

import json

from price_getter.sources.maxi import MAXI
from price_getter.sources.pcx import SUPERSTORE, extract_products_from_html, search_url

# Mirror of the real page's structures: a WebPage block with a ProductCollection
# nested under mainEntity, a second top-level collection, an unavailable
# product (no price), and a duplicate row to be deduped.
_PAGE = """
<html><head>
<script type="application/ld+json" data-next-head="">
{
  "@context": "https://schema.org/",
  "@type": "WebPage",
  "name": "Milk - Products For Sale | Maxi",
  "mainEntity": {
    "@context": "https://schema.org/",
    "@type": "ProductCollection",
    "offers": {
      "@type": "Offer",
      "itemOffered": [
        {
          "@context": "https://schema.org/",
          "@type": "Product",
          "name": "Purfiltre partially skimmed milk 2 %,  1.5 L",
          "url": "https://www.maxi.ca/fr/purfiltre-lait/p/20020563_EA",
          "image": "https://digital.loblaws.ca/PCX/20020563_EA/fr/1/x.png",
          "sku": "20020563_EA",
          "brand": {"@type": "Brand", "name": "Lactantia"},
          "offers": {"@type": "Offer", "price": 6.58, "priceCurrency": "CAD"}
        }
      ]
    }
  }
}
</script>
<script type="application/ld+json" data-next-head="">
{
  "@context": "https://schema.org/",
  "@type": "ProductCollection",
  "offers": {
    "@type": "Offer",
    "itemOffered": [
      {
        "@context": "https://schema.org/",
        "@type": "Product",
        "name": "Organic milk 3.8% M.F.",
        "brand": "Natrel",
        "offers": {"@type": "Offer", "price": 12.45, "priceCurrency": "CAD"}
      },
      {
        "@context": "https://schema.org/",
        "@type": "Product",
        "name": "Out of stock product",
        "offers": {"@type": "Offer", "priceCurrency": "CAD"}
      },
      {"@type": "Thing", "name": "not a product"}
    ]
  }
}
</script>
<script type="application/ld+json" data-next-head="">
{
  "@context": "https://schema.org/",
  "@type": "ProductCollection",
  "offers": {
    "@type": "Offer",
    "itemOffered": [
      {
        "@context": "https://schema.org/",
        "@type": "Product",
        "name": "Purfiltre partially skimmed milk 2 %,  1.5 L",
        "offers": {"@type": "Offer", "price": 6.58, "priceCurrency": "CAD"}
      }
    ]
  }
}
</script>
</head></html>
"""


def test_search_url_quotes_french_terms():
    assert (
        search_url(MAXI, "boeuf haché")
        == "https://www.maxi.ca/fr/search?search-bar=boeuf+hach%C3%A9&sort=relevance"
    )


def test_superstore_uses_english_search_and_its_origin():
    url = search_url(SUPERSTORE, "ground beef")
    assert url == (
        "https://www.realcanadiansuperstore.ca/en/search?search-bar=ground+beef&sort=relevance"
    ), "superstore needs origin realcanadiansuperstore.ca, not superstore.ca (BFF rejects it)"
    headers = SUPERSTORE.headers()
    assert headers["Origin"] == "https://www.realcanadiansuperstore.ca"
    assert headers["site-banner"] == "superstore"
    assert headers["Accept-Language"] == "en"


def test_extracts_products_from_nested_and_top_level_collections():
    products = extract_products_from_html(_PAGE)
    assert len(products) == 2

    purfiltre = products[0]
    assert (
        purfiltre["name"] == "Purfiltre partially skimmed milk 2 %, 1.5 L"
    )  # whitespace normalized
    assert str(purfiltre["price"]) == "6.58"
    assert purfiltre["currency"] == "CAD"
    assert purfiltre["brand"] == "Lactantia"
    assert purfiltre["image"].endswith("x.png")

    natrel = products[1]
    assert natrel["name"] == "Organic milk 3.8% M.F."
    assert str(natrel["price"]) == "12.45"
    assert natrel["brand"] == "Natrel"  # string brand is kept too


def test_skips_priceless_and_non_products_and_dedupes():
    products = extract_products_from_html(_PAGE)
    names = [p["name"] for p in products]
    assert "Out of stock product" not in names
    assert "not a product" not in names
    assert len([n for n in names if n == "Purfiltre partially skimmed milk 2 %, 1.5 L"]) == 1


def test_no_ld_json_blocks_returns_empty():
    assert (
        extract_products_from_html("<html><head><script>window.x = 1;</script></head></html>") == []
    )


def test_malformed_json_block_is_tolerated():
    html = '<script type="application/ld+json">{not json</script>' + json.dumps("") + ""
    assert extract_products_from_html(html) == []
