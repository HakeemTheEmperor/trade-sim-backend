from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.stocks_service import StocksService
from ..utils.auth_utils import require_api_key, role_required

bp = Blueprint("stocks", __name__, url_prefix="/api/v1/stocks")
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
            "data": stocks
        }), 200
    
@bp.route("/search/symbol/<symbol>", methods=["GET"])
@require_api_key()
@jwt_required()
def search_stock_by_symbol(symbol):
    result = stocks_service.search_stocks_by_symbol(symbol)
    if not result:
        return jsonify({"message": "Stock not found", "stocks": []}), 404
    return jsonify({
            "message": "Stocks retrieved successfully",
            "data": result
        }), 200
    
@bp.route("/symbol/<symbol>", methods=["GET"])
@require_api_key()
@jwt_required()
def get_stock_by_symbol(symbol):
    result = stocks_service.get_stock_by_exact_symbol(symbol)
    if not result:
        return jsonify({"message": "Stock not found", "stocks": []}), 404
    return jsonify({
            "message": "Stocks retrieved successfully",
            "data": result
        }), 200

@bp.route("/id/<id>", methods=["GET"])
@require_api_key()
@jwt_required()
def get_stock_by_id(id):
    result = stocks_service.get_stock_by_id(id)
    return jsonify({
        "message": "Stock retrieved successfully",
        "data": result
    }), 200

@bp.route("/search/company/<name>", methods=["GET"])
@require_api_key()
@jwt_required()
def get_stocks_by_company_name(name):
    result = stocks_service.get_stocks_by_company_name(name)
    if not result:
        return jsonify({"message": "Company not found", "stocks": []}), 404
    return jsonify({
        "message": "Stocks retrieved successfully",
        "data": result
        }), 200
    
@bp.route("/stock/price/<symbol>", methods=["GET"])
@require_api_key()
def get_stock_price(symbol):
    result = stocks_service.get_stocks_price(symbol)
    return jsonify({"message": "Stock price fetched successfully", "data": result}), 200

@bp.route("/buy", methods=["POST"])
@require_api_key()
@jwt_required()
def buy_stock():
    user_id = get_jwt_identity()
    data = request.get_json()
    if not data or not all(key in data for key in ["symbol", "quantity", "wallet_id"]):
        return jsonify({"error": "Missing required fields"}), 400
    symbol = data.get('symbol')
    quantity = data.get('quantity')
    wallet_id = data.get("wallet_id")
    message = stocks_service.buy_stocks(user_id, symbol, wallet_id, quantity)
    return jsonify(message), 200

@bp.route("/sell", methods=["POST"])
@require_api_key()
@jwt_required()
def sell_stock():
    user_id = get_jwt_identity()
    data = request.get_json()
    if not data or not all(key in data for key in ["symbol", "quantity", "wallet_id"]):
        return jsonify({"error": "Missing required fields"}), 400
    symbol = data.get('symbol')
    quantity = data.get('quantity')
    wallet_id = data.get("wallet_id")
    message = stocks_service.sell_stock(user_id, symbol, wallet_id, quantity)
    return jsonify(message), 200



@bp.route("/user", methods=["GET"])
@require_api_key()
@jwt_required()
def get_all_user_stocks():
    user_id = get_jwt_identity()
    result = stocks_service.get_all_user_stocks(user_id)
    return jsonify({"message": "Stocks retrieved successfully", "data": result}), 200

@bp.route("/user/quantity/<symbol>", methods=["GET"])
@require_api_key()
@jwt_required()
def get_user_stock_quantity(symbol):
    user_id = get_jwt_identity()
    result = stocks_service.get_user_stock_quantity(user_id, symbol)
    return jsonify({"message": "Stocks retrieved successfully", "data": result}), 200

@bp.route("/stock/history/<symbol>", methods=["GET"])
@require_api_key()
def get_stock_history(symbol):
    result = stocks_service.get_stock_history(symbol)
    return jsonify({
        "message": "Successfully retrieved stocks", "data": result
    }), 200


@bp.route("/portfolio", methods=["GET"])
@require_api_key()
@jwt_required()
def get_user_portfolio():
    user_id = get_jwt_identity()
    result = stocks_service.get_user_portfolio(user_id)
    return jsonify({
        "message": "Successfully retrieved stocks", "data": result
    }), 200

