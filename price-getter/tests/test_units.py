from decimal import Decimal

from price_getter.units import price_per_100g, price_per_liter


def test_price_per_100g_kilogram() -> None:
    assert price_per_100g("4.00", "1", "kg") == Decimal("0.4")


def test_price_per_100g_grams() -> None:
    assert price_per_100g("3.50", "250", "g") == Decimal("1.4")


def test_price_per_liter_milliliters() -> None:
    assert price_per_liter("2.50", "500", "ml") == Decimal("5.0")


def test_unknown_unit_returns_none() -> None:
    assert price_per_100g("2.00", "1", "bunch") is None
    assert price_per_liter("2.00", "1", "kg") is None


def test_missing_inputs_return_none() -> None:
    assert price_per_100g(None, "1", "kg") is None
    assert price_per_100g("1.00", None, "kg") is None
    assert price_per_100g("1.00", "1", None) is None


def test_zero_quantity_returns_none() -> None:
    assert price_per_100g("1.00", "0", "g") is None


def test_case_insensitive_units() -> None:
    assert price_per_100g("5.00", "1", "KG") == Decimal("0.5")
