"""Unit-price normalization so comparisons are fair across pack sizes.

Prices get rewritten to a canonical unit: per 100 g for anything sold by
weight, per liter for anything sold by volume. The database stores these in
`products.price_per_100g` / `products.price_per_l`.
"""

from decimal import Decimal, InvalidOperation

MASS_TO_GRAMS = {
    "g": Decimal(1),
    "kg": Decimal(1000),
    "oz": Decimal("28.3495"),
    "lb": Decimal("453.592"),
}

VOLUME_TO_LITERS = {
    "ml": Decimal("0.001"),
    "cl": Decimal("0.01"),
    "l": Decimal(1),
}

_CENTS = Decimal("0.0001")


def _num(value: Decimal | float | str | None) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None


def price_per_100g(
    price: Decimal | float | str | None,
    quantity: Decimal | float | str | None,
    unit: str | None,
) -> Decimal | None:
    """Price per 100 g, or None when the item isn't measurable by weight."""
    qty_grams = _scale_to(quantity, unit, MASS_TO_GRAMS)
    if qty_grams is None or qty_grams <= 0:
        return None
    p = _num(price)
    if p is None:
        return None
    return (p / qty_grams * 100).quantize(_CENTS)


def price_per_liter(
    price: Decimal | float | str | None,
    quantity: Decimal | float | str | None,
    unit: str | None,
) -> Decimal | None:
    """Price per liter, or None when the item isn't measurable by volume."""
    qty_liters = _scale_to(quantity, unit, VOLUME_TO_LITERS)
    if qty_liters is None or qty_liters <= 0:
        return None
    p = _num(price)
    if p is None:
        return None
    return (p / qty_liters).quantize(_CENTS)


def _scale_to(
    quantity: Decimal | float | str | None,
    unit: str | None,
    table: dict[str, Decimal],
) -> Decimal | None:
    if quantity is None or unit is None:
        return None
    factor = table.get(unit.strip().lower())
    qty = _num(quantity)
    if factor is None or qty is None:
        return None
    return qty * factor
