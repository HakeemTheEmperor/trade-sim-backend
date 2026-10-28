"""League and career tables: ranking, names, and one shared view per league."""
from decimal import Decimal

from app import db
from app.models.wallet import Wallet
from app.services.leaderboard_service import LeaderboardService
from app.services.league_service import LeagueService
from tests.factories import make_user, make_wallet


def make_league_of_three():
    """Three members who all start at 100,000, then end at +10%, flat and -10%."""
    winner = make_user(username="winner")
    flat = make_user(username="flat")
    loser = make_user(username="loser")
    wallets = {u.id: make_wallet(u, balance="100000") for u in (winner, flat, loser)}

    service = LeagueService()
    league = service.create_league(winner.id, "Friends")
    service.join_league(flat.id, league["join_code"])
    service.join_league(loser.id, league["join_code"])

    LeaderboardService().open_season()  # freezes every baseline at 100,000
    for user, balance in ((winner, "110000"), (flat, "100000"), (loser, "90000")):
        db.session.get(Wallet, wallets[user.id].id).balance = Decimal(balance)
    db.session.commit()
    return service, league["id"], (winner, flat, loser)


def entries(table):
    return [(e["rank"], e["username"], e["return_percent"]) for e in table["entries"]]


def test_season_table_ranks_members_by_return():
    service, league_id, (winner, flat, loser) = make_league_of_three()

    table = service.season_table(flat.id, league_id)

    assert entries(table) == [(1, "winner", 10.0), (2, "flat", 0.0), (3, "loser", -10.0)]
    assert table["viewer_ranked"] is True
    assert table["league"]["member_count"] == 3


def test_career_table_ranks_members_by_return_with_usernames():
    service, league_id, (winner, flat, loser) = make_league_of_three()

    table = service.career_table(loser.id, league_id)

    assert entries(table) == [(1, "winner", 10.0), (2, "flat", 0.0), (3, "loser", -10.0)]


def test_every_member_sees_the_same_table():
    service, league_id, members = make_league_of_three()

    tables = [entries(service.season_table(m.id, league_id)) for m in members]

    assert tables[0] == tables[1] == tables[2]
