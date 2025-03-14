from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.custom_exceptions import MissingProperties
from ..services.wallet_service import WalletService, WalletCurrencyType
from ..utils.auth_utils import require_api_key, role_required

bp = Blueprint("wallet", __name__, url_prefix="/api/v1/wallet")
wallet_service = WalletService()

@bp.route("/all", methods=["GET"])
@require_api_key()
@jwt_required()
def get_all_user_wallets():
    user_id = get_jwt_identity()
    wallets = wallet_service.get_user_wallets(user_id)
    if not wallets:
        return jsonify({"message": "No wallets found for this user", "wallets": []}), 404
    return jsonify({
        "message": "Wallets retrieved successfully",
        "wallets": wallets
    }), 200
    
@bp.route("/<int:wallet_id>", methods=["GET"])
@require_api_key()
@jwt_required()
def get_user_wallet_by_id(wallet_id):
    user_id = get_jwt_identity()
    wallet = wallet_service.get_wallet_by_id(user_id, wallet_id)
    return jsonify({
        "message": "Wallet retrieved successfully",
        "wallet": wallet
    })
    
@bp.route("/create", methods=["POST"])
@require_api_key()
@jwt_required()
def create_wallet():
    user_id = get_jwt_identity()
    currency = request.args.get("currency")
    new_wallet = wallet_service.create_wallet(user_id, currency)
    return jsonify({
        "message": "Wallet Created Successfully",
        "wallet": new_wallet
    }), 201
    
@bp.route('/delete', methods=['DELETE'])
@require_api_key()
@jwt_required()
def delete_wallet():
    user_id = get_jwt_identity()
    wallet_id = request.args.get("wallet_id")
    if not wallet_id:
        return jsonify({
            "message": "Wallet ID is required"
        }), 400
    response = wallet_service.delete_wallet(user_id, wallet_id)
    return jsonify(response), 200

@bp.route('/transfer', methods=['POST'])
@require_api_key()
@jwt_required()
def wallet_transfer():
    user_id = get_jwt_identity()
    data = request.get_json()
    if not data or not all(key in data for key in ["from_wallet_id", "to_wallet_id", "amount"]):
        return jsonify({
            'message': "Missing sender/receiver wallet or amount",
            'status': "MISSING REQUIRED PROPERTIES",
            'error_code': 400
        }), 400
    print("Got here")
    from_wallet_id = data["from_wallet_id"]
    to_wallet_id = data["to_wallet_id"]
    amount = data["amount"]

    
    response = wallet_service.transfer_funds(from_wallet_id, to_wallet_id, amount, user_id)
    return jsonify(response), 200
