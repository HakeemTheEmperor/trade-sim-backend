from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..utils.auth_utils import require_api_key, role_required
from ..services.watchlist_service import WatchlistService

bp = Blueprint("watchlist", __name__, url_prefix="/api/v1/watchlist")
watchlist_service = WatchlistService()

@bp.route("/add/<symbol>", methods=["POST"])
@require_api_key()
@jwt_required()
def add_watchlist_item(symbol):
    """Add a new item to the user's watchlist."""
    user_id = get_jwt_identity()
    symbol = symbol.strip().upper()
    response = watchlist_service.add_to_watchlist(user_id, symbol)
    return jsonify(response), 200

@bp.route("/get", methods=["GET"])
@require_api_key()
@jwt_required()
def get_watchlist():
    user_id = get_jwt_identity()
    watchlist = watchlist_service.get_from_watchlist(user_id)
    return jsonify({
        "message": "Successfully got user watchlist",
        "data": watchlist
        }), 200

@bp.route("/delete/<symbol>", methods=["DELETE"])
@require_api_key()
@jwt_required()
def delete_watchlist_item(symbol):
    user_id = get_jwt_identity()
    symbol = symbol.strip().upper()
    response = watchlist_service.remove_from_watchlist(user_id, symbol)
    return jsonify(response), 200

@bp.route("/check/<symbol>", methods=["GET"])
@require_api_key()
@jwt_required()
def check_watchlist_item(symbol):
    user_id = get_jwt_identity()
    symbol = symbol.strip().upper()
    
    result = watchlist_service.is_in_watchlist(user_id, symbol)
    if result == True:
        return jsonify({"message": f"{symbol} in watchlist", "data": result})
    if result == False:
        return jsonify({"message": f"{symbol} not in watchlist", "data": result})