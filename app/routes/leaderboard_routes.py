from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required

from ..services.leaderboard_service import LeaderboardService

bp = Blueprint("leaderboard", __name__, url_prefix="/api/v1/leaderboard")
leaderboard_service = LeaderboardService()

# The friend-board endpoints that used to live here are gone. They ranked an
# ego-centric cohort derived from shadow links, so no two people saw the same
# table and nobody could talk about "the standings" — there weren't any.
# Rankings now live under /api/v1/leagues, where a table is a shared object.
#
# The shadow graph keeps its actual job: trade notifications. Only the ranking
# moved.


@bp.route("/season", methods=["GET"])
@jwt_required()
def current_season():
    """The running season. Not league-specific — every league is ranked over
    the same window, and the client needs the dates before picking a league."""
    season = leaderboard_service.current_season()
    if not season:
        return jsonify({"season": None, "message": "No season is currently running"}), 200
    return jsonify({"season": season.to_dict()}), 200
