"""Single source of truth for every outbound third-party API endpoint.

When a provider changes a path or you need to point at a sandbox, this is the
ONE file to edit — the services just call these helpers and never build URLs
themselves.

Convention:
- Base URLs come from env (with a sensible default) so they're overridable per
  environment / for tests, without hardcoding secrets or scattering them.
- API keys come from env (never defaulted).
- Both are read at call time, so import order relative to load_dotenv() can't
  bite us.
"""
import os


class FMP:
    """Financial Modeling Prep — company profiles + seed prices."""

    @staticmethod
    def base():
        return os.getenv("FMP_BASE_URL", "https://financialmodelingprep.com/stable")

    @staticmethod
    def profile_url(symbol):
        return f"{FMP.base()}/profile?symbol={symbol}&apikey={os.getenv('FMP_API_KEY')}"


class Polygon:
    """Polygon.io — daily price history (aggregates)."""

    @staticmethod
    def base():
        return os.getenv("POLYGON_BASE_URL", "https://api.massive.com ")

    @staticmethod
    def daily_aggs_url(symbol, start_date, end_date, limit=120):
        return (
            f"{Polygon.base()}/v2/aggs/ticker/{symbol}/range/1/day/{start_date}/{end_date}"
            f"?adjusted=true&sort=asc&limit={limit}&apiKey={os.getenv('POLYGON_API_KEY')}"
        )


class Finnhub:
    """Finnhub — real-time price websocket."""

    @staticmethod
    def base():
        return os.getenv("FINNHUB_WS_URL", "wss://ws.finnhub.io")

    @staticmethod
    def ws_url():
        return f"{Finnhub.base()}?token={os.getenv('FINNHUB_API_KEY')}"


class ExchangeRate:
    """exchangerate-api.com. EXCHANGE_RATE_API is the base incl. the key segment,
    e.g. https://v6.exchangerate-api.com/v6/YOUR-KEY (NO trailing /pair or /latest).

    We use the /latest/{base} endpoint: one call returns every target rate
    (conversion_rates) plus time_next_update_unix, so we fetch once per provider
    update and derive all pairs (incl. reciprocals) from it."""

    @staticmethod
    def base():
        return os.getenv("EXCHANGE_RATE_API")

    @staticmethod
    def latest_url(base_currency):
        return f"{ExchangeRate.base()}/latest/{base_currency}"
