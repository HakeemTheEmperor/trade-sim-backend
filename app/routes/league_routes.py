from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..services.league_service import LeagueService
from ..utils.rate_limit import rate_limit

bp = Blueprint("leagues", __name__, url_prefix="/api/v1/leagues")
league_service = LeagueService()


@bp.route("", methods=["GET"])
@jwt_required()
def my_leagues():
    return jsonify({"leagues": league_service.my_leagues(get_jwt_identity())}), 200


@bp.route("", methods=["POST"])
@jwt_required()
@rate_limit(max_requests=10, window_seconds=3600)
def create_league():
    data = request.get_json() or {}
    league = league_service.create_league(get_jwt_identity(), data.get("name"))
    return jsonify({"message": "League created", "league": league}), 201


@bp.route("/join", methods=["POST"])
@jwt_required()
# Rate limited because the join code is the only thing standing between a
# stranger and a league. 8 characters from a 31-character alphabet is ~8.5e11
# combinations, which is only out of reach if guesses are capped.
@rate_limit(max_requests=10, window_seconds=300)
def join_league():
    data = request.get_json() or {}
    league = league_service.join_league(get_jwt_identity(), data.get("code"))
    return jsonify({"message": f"You have joined {league['name']}", "league": league}), 200


@bp.route("/<int:league_id>", methods=["GET"])
@jwt_required()
def season_table(league_id):
    return jsonify(league_service.season_table(get_jwt_identity(), league_id)), 200


@bp.route("/<int:league_id>/career", methods=["GET"])
@jwt_required()
def career_table(league_id):
    return jsonify(league_service.career_table(get_jwt_identity(), league_id)), 200


@bp.route("/<int:league_id>/leave", methods=["DELETE"])
@jwt_required()
def leave_league(league_id):
    return jsonify(league_service.leave_league(get_jwt_identity(), league_id)), 200


@bp.route("/<int:league_id>", methods=["DELETE"])
@jwt_required()
def delete_league(league_id):
    return jsonify(league_service.delete_league(get_jwt_identity(), league_id)), 200
