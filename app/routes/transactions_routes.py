from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.transactions_service import TransactionsService, TransactionCategory
from ..services.wallet_service import WalletCurrencyType
from ..utils.auth_utils import require_api_key, role_required

bp = Blueprint("transactions", __name__, url_prefix="/api/v1/transactions")
transaction_service = TransactionsService()

@bp.route("/history", methods=["GET"])
@require_api_key()
@jwt_required()
def get_user_transactions_history():
    user_id = get_jwt_identity()
    wallet_id = request.args.get("wallet_id")
    currency = request.args.get("currency")
    transaction_category = request.args.get("category")
    sort = request.args.get("sort_by")
    page = request.args.get("page")
    rows = request.args.get("limit")
    result = transaction_service.get_transaction_history(user_id, wallet_id, currency, transaction_category, sort, page, rows)
    return jsonify(result), 200