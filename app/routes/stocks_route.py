from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.stocks_service import StocksService
from ..utils.auth_utils import require_api_key, role_required

bp = Blueprint("stocks", __name__, url_prefix="/stocks")
stocks_service = StocksService()

@bp.route("/all", methods=["GET"])
@require_api_key()
@jwt_required()
def get_all_stocks():
    stocks = stocks_service.get_available_stocks()
    if not stocks:
        return jsonify({"error": "No available stocks"}), 404
    return jsonify({
            "message": "Stocks retrieved successfully",
            "stocks": stocks
        }), 200