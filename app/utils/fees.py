"""Trading and transfer costs, in one place.

Modelled on how retail brokers actually make money in 2026, which is NOT flat
commissions — those are largely gone from US retail. The two costs that are
always present are:

  * the BID-ASK SPREAD on a trade. There are two prices at any moment: you buy
    at the ask and sell at the bid. You eat the difference immediately, which is
    why you are slightly down the instant you buy. Modelled here as a half
    spread applied either side of the quoted price.

  * the FX MARKUP on a currency conversion, typically 0.3%-1.5% retail. This is
    where brokers and money apps make serious margin, and it is invisible to
    most users because it is baked into the rate they are shown.

Both are percentage-based on purpose. A flat minimum fee would exceed the
proceeds of a small sale and drive a balance negative; a percentage cannot.

Rates are env-overridable so they can be tuned without a deploy, but note that
CHANGING THEM RETROACTIVELY CHANGES LEADERBOARD FAIRNESS — two players who made
the same trades in different seasons would pay different costs. Prefer changing
them at a season boundary.
"""
import logging
import os
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)

# Half-spread applied either side of the quoted price: buys execute above it,
# sells below. 0.0005 = 5 basis points, so a round trip costs ~0.1%.
#
# Real large-cap spreads are tighter than this (a cent or two on a $200 share is
# ~0.005%), but a retail order also pays slippage and the market maker's edge via
# payment for order flow. 5bp keeps the lesson visible: churning costs you.
DEFAULT_TRADE_HALF_SPREAD = "0.0005"

# Markup on cross-currency transfers, taken from the converted amount.
# 0.005 = 0.5%, which sits mid-range for retail: Wise/Revolut land around
# 0.3-0.6%, mainstream brokers 0.35-1.5%, and only near-wholesale desks go lower.
DEFAULT_FX_SPREAD = "0.005"


def _decimal_env(name, default):
    """Read a Decimal rate from env, refusing values that make no sense.

    A typo here silently changes what every user pays, so a bad value falls back
    to the default loudly rather than being applied. Rates must be in [0, 0.5):
    negative would pay users to trade, and anything approaching half the trade
    value is a bug, not a pricing decision.
    """
    raw = os.getenv(name, default).strip()
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError):
        logger.warning("%s=%r is not a number; falling back to %s", name, raw, default)
        return Decimal(default)
    if value < 0 or value >= Decimal("0.5"):
        logger.warning("%s=%s is out of range [0, 0.5); falling back to %s", name, value, default)
        return Decimal(default)
    return value


def trade_half_spread():
    return _decimal_env("TRADE_HALF_SPREAD", DEFAULT_TRADE_HALF_SPREAD)


def fx_spread():
    return _decimal_env("FX_SPREAD", DEFAULT_FX_SPREAD)


def buy_execution_price(quoted_price):
    """What a buyer actually pays per share: the ask side of the quote."""
    return Decimal(quoted_price) * (Decimal(1) + trade_half_spread())


def sell_execution_price(quoted_price):
    """What a seller actually receives per share: the bid side of the quote."""
    return Decimal(quoted_price) * (Decimal(1) - trade_half_spread())
