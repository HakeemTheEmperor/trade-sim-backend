"""League table cost at 10,000 users: the batched live query vs a per-member loop.

Context that shapes what is measured. League tables are computed LIVE (see
LeagueService._equity_for), not read from equity_snapshots, so "snapshot vs
live" is not a comparison the app makes. The comparison that exists is how the
live table is assembled:

  current   LeagueService.season_table: equity for the whole cohort in a fixed
            number of batched queries
  baseline  the same table built by calling LeaderboardService.compute_equity
            once per member (the approach the batching replaced); price and rate
            caches are shared across members, as the nightly job shares them, so
            the baseline is not handicapped
  snapshot  reading today's equity_snapshots rows: the fast-but-stale
            alternative, timed for reference only

A league is capped at MAX_LEAGUE_MEMBERS (50), so league size, not the 10,000
users, sets the work. The users exist so Postgres plans the queries against
realistic table sizes (index vs sequential scan) rather than near-empty tables.
"""
import statistics
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import event, insert, select, text

from app import db
from app.models.leaderboard import EquitySnapshot, Season, SeasonParticipant
from app.models.league import League, LeagueMembership
from app.models.stock_available import AvailableStocks
from app.models.stock_price import StockPrice
from app.models.user import User, UserRoles
from app.models.user_stock_wallet import UserStockWallet
from app.models.wallet import Wallet, WalletCurrencyType
from app.services.league_service import LeagueService
from app.services.leaderboard_service import LeaderboardService

pytestmark = pytest.mark.perf

USERS = 10_000
SYMBOLS = 200
HOLDINGS_PER_USER = 5
LEAGUE_SIZE = 50  # the product cap, MAX_LEAGUE_MEMBERS
RUNS = 15
WARMUP = 3
STARTING_EQUITY = Decimal("100000")


def _price(i):
    return Decimal(1000 + (i * 7919) % 49000) / 100  # 10.00 .. 499.99


def _balance(g):
    return Decimal(5_000_000 + (g * 7919) % 5_000_000) / 100  # 50,000.00 .. 99,999.99


def _holdings(g):
    """(symbol index, quantity) pairs. 37 is coprime to 200, so a user's five
    symbols are always distinct. Two-decimal prices times two-decimal quantities
    are exact to four places, so the oracle below needs no rounding."""
    return [((g + k * 37) % SYMBOLS, Decimal(100 + (g * (k + 3)) % 2000) / 100)
            for k in range(HOLDINGS_PER_USER)]


@pytest.fixture
def seeded():
    """10,000 users with wallets and holdings, a running season, today's
    snapshots and one 50-member league. Returns the oracle's equity per user id."""
    started = time.perf_counter()
    now = datetime.now(timezone.utc)

    symbols = [f"S{i:03d}" for i in range(SYMBOLS)]
    db.session.execute(insert(AvailableStocks), [
        {"symbol": s, "company_name": f"{s} Inc.", "industry": "Testing", "market_cap": 1_000_000_000,
         "sector": "Technology", "image": "https://example.com/x.png",
         "website": "https://example.com", "description": "Fixture."}
        for s in symbols
    ])
    db.session.execute(insert(StockPrice), [
        {"symbol": s, "current_price": _price(i)} for i, s in enumerate(symbols)
    ])

    db.session.execute(insert(User), [
        {"first_name": "Perf", "last_name": "User", "username": f"perf_{g}",
         "email": f"perf_{g}@example.com", "password_hash": "x", "is_verified": True,
         "role": UserRoles.USER}
        for g in range(1, USERS + 1)
    ])
    ids = [row[0] for row in db.session.execute(select(User.id).order_by(User.id))]
    assert len(ids) == USERS

    equity = {}
    wallets, holdings, participants, snapshots = [], [], [], []
    today = now.date()
    for g, uid in enumerate(ids, start=1):
        cash = _balance(g)
        held = Decimal(0)
        for index, quantity in _holdings(g):
            holdings.append({"user_id": uid, "symbol": symbols[index], "quantity": quantity})
            held += quantity * _price(index)
        wallets.append({"user_id": uid, "balance": cash, "currency": WalletCurrencyType.USD})
        equity[uid] = cash + held
        snapshots.append({"user_id": uid, "captured_on": today, "equity": cash + held,
                          "cash": cash, "holdings": held})

    season = Season(name="Perf season", starts_at=now - timedelta(days=1), ends_at=now + timedelta(days=89))
    db.session.add(season)
    db.session.flush()
    participants = [{"season_id": season.id, "user_id": uid, "baseline_equity": STARTING_EQUITY}
                    for uid in ids]

    db.session.execute(insert(Wallet), wallets)
    db.session.execute(insert(UserStockWallet), holdings)
    db.session.execute(insert(SeasonParticipant), participants)
    db.session.execute(insert(EquitySnapshot), snapshots)

    league = League(name="Perf league", join_code="PERFTEST", owner_id=ids[0])
    db.session.add(league)
    db.session.flush()
    db.session.add_all(LeagueMembership(league_id=league.id, user_id=uid) for uid in ids[:LEAGUE_SIZE])
    db.session.commit()
    db.session.execute(text("ANALYZE"))  # plans must reflect the data, not an empty table's stats
    db.session.commit()

    print(f"\n  seeded {USERS} users, {len(holdings)} holdings in {time.perf_counter() - started:.1f}s")
    return {"ids": ids, "equity": equity, "league_id": league.id, "viewer": ids[0],
            "members": ids[:LEAGUE_SIZE]}


class QueryRecorder:
    """Captures every SELECT the code under test sends, with its parameters."""

    def __init__(self):
        self.selects = []

    def _on(self, conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            self.selects.append((statement, parameters))

    def __enter__(self):
        event.listen(db.engine, "before_cursor_execute", self._on)
        return self

    def __exit__(self, *exc):
        event.remove(db.engine, "before_cursor_execute", self._on)


def current_table(seed):
    result = LeagueService().season_table(seed["viewer"], seed["league_id"])
    return {e["user_id"]: e["return_percent"] for e in result["entries"]}


def per_member_table(seed):
    service = LeaderboardService()
    members = [m.user_id for m in LeagueMembership.query.filter_by(league_id=seed["league_id"]).all()]
    season = service.current_season()
    participants = SeasonParticipant.query.filter(
        SeasonParticipant.season_id == season.id, SeasonParticipant.user_id.in_(members)).all()
    prices, rates = {}, {}
    table = {}
    for p in participants:
        value, _, _ = service.compute_equity(p.user_id, prices, rates)
        change = (value - Decimal(p.baseline_equity)) / Decimal(p.baseline_equity) * 100
        table[int(p.user_id)] = float(round(change, 3))
    return table


def snapshot_table(seed):
    service = LeaderboardService()
    members = [m.user_id for m in LeagueMembership.query.filter_by(league_id=seed["league_id"]).all()]
    season = service.current_season()
    participants = SeasonParticipant.query.filter(
        SeasonParticipant.season_id == season.id, SeasonParticipant.user_id.in_(members)).all()
    today = datetime.now(timezone.utc).date()
    equity = dict(db.session.query(EquitySnapshot.user_id, EquitySnapshot.equity).filter(
        EquitySnapshot.user_id.in_(members), EquitySnapshot.captured_on == today).all())
    table = {}
    for p in participants:
        change = (Decimal(equity[p.user_id]) - Decimal(p.baseline_equity)) / Decimal(p.baseline_equity) * 100
        table[int(p.user_id)] = float(round(change, 3))
    return table


def timed(fn):
    """Median and worst of RUNS runs, each from a fresh session like a real request."""
    for _ in range(WARMUP):
        db.session.remove()
        fn()
    samples = []
    for _ in range(RUNS):
        db.session.remove()
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000)
    return statistics.median(samples), max(samples)


def explain(statements):
    """EXPLAIN (ANALYZE, BUFFERS) each distinct statement, with its real parameters."""
    seen = set()
    for statement, parameters in statements:
        if statement in seen:
            continue
        seen.add(statement)
        plan = db.session.connection().exec_driver_sql(
            "EXPLAIN (ANALYZE, BUFFERS) " + statement, parameters).all()
        tables = " ".join(statement.split("FROM", 1)[1].split()[:1]) if "FROM" in statement else "?"
        print(f"\n  --- SELECT ... FROM {tables}")
        for (line,) in plan:
            print(f"    {line}")


def test_league_table_is_correct_and_fast_at_10k_users(seeded, capsys):
    seed = seeded

    # Independent oracle: expected returns straight from the seed arithmetic.
    expected = {
        uid: float(round((seed["equity"][uid] - STARTING_EQUITY) / STARTING_EQUITY * 100, 3))
        for uid in seed["members"]
    }
    db.session.remove()
    assert current_table(seed) == expected
    db.session.remove()
    assert per_member_table(seed) == expected
    db.session.remove()
    assert snapshot_table(seed) == expected

    db.session.remove()
    with QueryRecorder() as current_queries:
        current_table(seed)
    db.session.remove()
    with QueryRecorder() as baseline_queries:
        per_member_table(seed)

    current_ms, current_worst = timed(lambda: current_table(seed))
    baseline_ms, baseline_worst = timed(lambda: per_member_table(seed))
    snapshot_ms, snapshot_worst = timed(lambda: snapshot_table(seed))

    with capsys.disabled():
        print(f"\n  League of {LEAGUE_SIZE} in a database of {USERS:,} users; median of {RUNS} runs "
              f"(worst in brackets), local Postgres, fresh session per run")
        print(f"    current  (batched live):      {current_ms:7.1f} ms  [{current_worst:.1f}]  "
              f"{len(current_queries.selects)} SELECTs")
        print(f"    baseline (per-member loop):   {baseline_ms:7.1f} ms  [{baseline_worst:.1f}]  "
              f"{len(baseline_queries.selects)} SELECTs")
        print(f"    snapshot (stale, reference):  {snapshot_ms:7.1f} ms  [{snapshot_worst:.1f}]")
        print("\n  EXPLAIN (ANALYZE, BUFFERS) for the current path, one plan per distinct query:")
        explain(current_queries.selects)
        print(f"\n  RESULT: League table in {current_ms:.0f} ms instead of {baseline_ms:.0f} ms\n")

    assert current_ms < baseline_ms
