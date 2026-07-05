import math


def validate_positive_number(value, field_name="value"):
    """Coerce ``value`` to a strictly-positive, finite float.

    Guards the money/quantity paths against the classic exploits:
    non-numeric input, negative values (which flip subtraction into a credit),
    and NaN/inf (note: ``float("nan") <= 0`` is ``False``, so a naive ``> 0``
    check alone is bypassable). Raises ``ValueError`` on any invalid input so
    the existing ValueError handler returns a clean 400.
    """
    if value is None:
        raise ValueError(f"{field_name} is required")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a valid number")
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be a valid number")
    if number <= 0:
        raise ValueError(f"{field_name} must be greater than zero")
    return number


def validate_wallet_id(value, field_name="wallet id"):
    """Coerce a wallet id to a positive int, rejecting junk/negative ids."""
    try:
        wallet_id = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a valid whole number")
    if wallet_id <= 0:
        raise ValueError(f"{field_name} must be greater than zero")
    return wallet_id


def clamp_pagination(page, rows, default_rows=10, max_rows=100):
    """Safely coerce/clamp pagination params.

    Bad input falls back to defaults, and ``rows`` is capped at ``max_rows`` so a
    client can't request an unbounded page size (e.g. ``?limit=10000000``) and
    exhaust memory. Also tolerates non-numeric input, which the old
    ``int(page)`` path would have raised on.
    """
    try:
        page = int(page)
    except (TypeError, ValueError):
        page = 1
    try:
        rows = int(rows)
    except (TypeError, ValueError):
        rows = default_rows
    if page < 1:
        page = 1
    if rows < 1:
        rows = default_rows
    if rows > max_rows:
        rows = max_rows
    return page, rows
