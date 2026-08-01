from flask import Blueprint, jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..services.leaderboard_service import LeaderboardService

bp = Blueprint("leaderboard", __name__, url_prefix="/api/v1/leaderboard")
leaderboard_service = LeaderboardService()


@bp.route("/friends", methods=["GET"])
@jwt_required()
def friends_board():
    """Current season, ranked among the caller's accepted shadow connections.

    Returns percentage return only — no balances. A board that published equity
    would contradict the privacy rule the shadow feature is built on, where
    trade notifications deliberately carry no amounts.
    """
    user_id = get_jwt_identity()
    return jsonify(leaderboard_service.friend_board(user_id)), 200


@bp.route("/friends/career", methods=["GET"])
@jwt_required()
def career_board():
    """All-time board over the same cohort: return since the starting grant."""
    user_id = get_jwt_identity()
    return jsonify(leaderboard_service.career_board(user_id)), 200


@bp.route("/season", methods=["GET"])
@jwt_required()
def current_season():
    season = leaderboard_service.current_season()
    if not season:
        return jsonify({"season": None, "message": "No season is currently running"}), 200
    return jsonify({"season": season.to_dict()}), 200
