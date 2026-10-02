ZERO_DECIMAL_CURRENCIES = {"JPY", "KRW", "VND", "CLP"}


def to_major(amount_minor: int, currency: str) -> float:
    """Razorpay amounts are in the smallest unit (paise); Zoho amounts are in rupees."""
    if currency.upper() in ZERO_DECIMAL_CURRENCIES:
        return float(amount_minor)
    return amount_minor / 100


def same_amount(a: float | None, b: float | None) -> bool:
    return a is not None and b is not None and abs(float(a) - float(b)) < 0.01
