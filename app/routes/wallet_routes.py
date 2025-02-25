from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token, jwt_required, get_jwt, get_jwt_identity
from ..services.wallet_service import WalletService, WalletCurrencyType
from ..utils.auth_utils import require_api_key, role_required

bp = Blueprint("wallet", __name__, url_prefix="/wallet")
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
    })
    
@bp.route("/<int:wallet_id>", methods=["GET"])
@require_api_key()
@jwt_required()
def get_user_wallet_by_id(wallet_id):
    user_id = get_jwt_identity()
    wallet = wallet_service.get_wallet_by_id(user_id, wallet_id)
    if not wallet:
        return jsonify({
            "message": "Wallet not found",
        }), 404
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
    if not currency:
        return jsonify({
            "message": "Currency is required"
        }), 400
        
    try:
        currency_enum = WalletCurrencyType[currency]
    except KeyError:
        return jsonify({
            "message": "Invalid currency type"
        }), 400
    
    # Check if the user already has a wallet with the given currency
    existing_wallet = wallet_service.get_wallet_by_currency(user_id, currency_enum)
    if existing_wallet:
        return jsonify({
            "message": "A wallet with this currency already exists"
        }), 409
    new_wallet = wallet_service.create_wallet(user_id, currency_enum)
    return jsonify({
        "message": "Wallet Created Successfully",
        "wallet": new_wallet
    }), 201
    
@bp.route('/delete', methods=['POST'])
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
            "error": "Missing required fields (sender_wallet_id, receiver_wallet_id, amount)"
        }), 400
    
    from_wallet_id = data["from_wallet_id"]
    to_wallet_id = data["to_wallet_id"]
    amount = int(data["amount"])
    
    response = wallet_service.transfer_funds(from_wallet_id, to_wallet_id, amount, user_id)
    return jsonify(response), 200
