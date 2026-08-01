from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required

from ..utils.fees import fx_spread, trade_half_spread

bp = Blueprint("config", __name__, url_prefix="/api/v1/config")


@bp.route("/trading", methods=["GET"])
@jwt_required()
def trading_config():
    """The cost rates the server will actually apply.

    Exists so the client can quote an accurate figure before a trade instead of
    hardcoding its own copy of the rates. A duplicated constant would drift the
    moment TRADE_HALF_SPREAD is tuned, and the failure is nasty rather than
    obvious: the estimate quietly understates the charge, so a user spending
    their whole balance is told "Insufficient balance" by a screen that just
    promised them it would fit.

    Not secret — these are disclosed to the user anyway — but authenticated to
    avoid adding an unauthenticated surface for no reason.
    """
    return jsonify({
        "trade_half_spread": float(trade_half_spread()),
        "fx_spread": float(fx_spread()),
    }), 200
