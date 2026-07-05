from flask import jsonify
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import HTTPException
from .custom_exceptions import AlreadyExists, DataNotFound, InsufficientFunds, LimitReached, MissingProperties, WalletNotFound

def register_error_handlers(app):
    @app.errorhandler(ValueError)
    def handle_value_error(e):
        # ValueErrors are raised deliberately for user-facing validation
        # messages (e.g. "Amount must be greater than zero"), so it's safe to
        # surface the message.
        return jsonify({
            'message': str(e),
            'status': 'Value Error',
            'error_code': 400
            }), 400

    @app.errorhandler(IntegrityError)
    def handle_integrity_error(e):
        return jsonify({
            'message': 'Database error, please try again',
            'status': 'INTEGRITY ERROR',
            'error_code': 409}), 409

    @app.errorhandler(RuntimeError)
    def handle_runtime_error(e):
        # Services wrap arbitrary exceptions as RuntimeError(str(e)), which can
        # carry SQL/driver internals. Log the detail server-side, return generic.
        app.logger.exception("Unhandled runtime error")
        return jsonify({
            'message': 'An unexpected error occurred. Please try again later.',
            'status': 'RUNTIME ERROR',
            'error_code': 500}), 500
    
    @app.errorhandler(KeyError)
    def handle_key_error(e):
        return jsonify({
            'message': 'Invalid request', 
            'status': 'Key Error',
            'error_code': 400
                }), 400
    
    @app.errorhandler(MissingProperties)
    def handle_missing_properties_error(e):
        return jsonify({
            'message': str(e),
            'status': e.status,
            'error_code': 400
        }), 400
    
    @app.errorhandler(LimitReached)
    def handle_limit_reached_error(e):
        return jsonify({
            'message': str(e),
            'status': e.status,
            'error_code': 400
        }), 403
        
    @app.errorhandler(WalletNotFound)
    def handle_wallet_not_found_error(e):
        return jsonify({
            'message': str(e),
            'status': 'Wallet Not Found Error',
            'error_code': 404
        }), 404
    
    @app.errorhandler(AlreadyExists)
    def handle_already_exists(e):
        return jsonify({
            'message': str(e),
            'status': e.status,
            'error_code': 409
        }), 409
    
    @app.errorhandler(DataNotFound)
    def handle_data_not_found(e):
        return jsonify({
            'message': str(e),
            'status': e.status,
            'error_code': 404
        }), 404
    
    @app.errorhandler(InsufficientFunds)
    def handle_insufficient_funds(e):
        return jsonify({
            'message': str(e),
            'status': 'Insufficient Funds Error',
            'error_code': 403
        }), 403

    @app.errorhandler(Exception)
    def handle_unexpected_error(e):
        # Preserve genuine HTTP errors (404, 405, 401, ...) so they keep their
        # status and don't get masked as 500s.
        if isinstance(e, HTTPException):
            return e
        # Anything else is unexpected: log the detail, return a generic 500 so
        # stack traces / internals never reach the client.
        app.logger.exception("Unhandled exception")
        return jsonify({
            'message': 'An unexpected error occurred. Please try again later.',
            'status': 'INTERNAL SERVER ERROR',
            'error_code': 500
        }), 500