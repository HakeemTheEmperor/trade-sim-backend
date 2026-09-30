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
    """Massive (formerly Polygon.io) — daily price history (aggregates).

    api.polygon.io still resolves and is kept working in parallel, but
    api.massive.com is the current default.
    """

    @staticmethod
    def base():
        return os.getenv("POLYGON_BASE_URL", "https://api.massive.com")

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

    @staticmethod
    def rest_base():
        return os.getenv("FINNHUB_BASE_URL") or "https://finnhub.io/api/v1"

    @staticmethod
    def profile_url(symbol):
        return f"{Finnhub.rest_base()}/stock/profile2?symbol={symbol}"

    @staticmethod
    def headers():
        # Header rather than query string, so the key stays out of URLs and logs.
        return {"X-Finnhub-Token": os.getenv("FINNHUB_API_KEY")}


class Alpaca:
    """Alpaca Market Data — bulk latest-trade snapshots for the long tail of
    tickers the Finnhub websocket can't cover.

    Credentials go in headers, not the URL. The free plan only serves the IEX
    feed, so ``feed`` defaults to ``iex``.
    """

    @staticmethod
    def base():
        return os.getenv("ALPACA_DATA_URL") or "https://data.alpaca.markets"

    @staticmethod
    def snapshots_url():
        return f"{Alpaca.base()}/v2/stocks/snapshots"

    @staticmethod
    def feed():
        return os.getenv("ALPACA_FEED") or "iex"

    @staticmethod
    def bars_url():
        return f"{Alpaca.base()}/v2/stocks/bars"

    @staticmethod
    def history_feed():
        """Feed for historical daily bars. Unlike live data, the Basic plan can
        read consolidated SIP history as long as it's over 15 minutes old."""
        return os.getenv("ALPACA_HISTORY_FEED") or "sip"

    @staticmethod
    def configured():
        return bool(os.getenv("ALPACA_API_KEY_ID") and os.getenv("ALPACA_API_SECRET_KEY"))

    @staticmethod
    def headers():
        return {
            "APCA-API-KEY-ID": os.getenv("ALPACA_API_KEY_ID"),
            "APCA-API-SECRET-KEY": os.getenv("ALPACA_API_SECRET_KEY"),
        }


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


class Brevo:
    """Brevo (ex-Sendinblue) — transactional email (OTP delivery).

    The key goes in an ``api-key`` header rather than the query string, so unlike
    the price providers above the URL helper carries no secret. Sending requires
    a sender that Brevo has verified (a confirmed address or an authenticated
    domain); an unverified sender is accepted by the API and then silently not
    delivered, so verify it in the dashboard before relying on this.
    """

    @staticmethod
    def base():
        return os.getenv("BREVO_BASE_URL", "https://api.brevo.com/v3")

    @staticmethod
    def send_email_url():
        return f"{Brevo.base()}/smtp/email"

    @staticmethod
    def api_key():
        return os.getenv("BREVO_API_KEY")

    @staticmethod
    def sender():
        return {
            "name": os.getenv("BREVO_SENDER_NAME", "iMockMarket"),
            "email": os.getenv("BREVO_SENDER_EMAIL"),
        }
