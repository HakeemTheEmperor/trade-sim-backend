from flask import jsonify
from sqlalchemy.exc import IntegrityError
from .custom_exceptions import AlreadyExists, DataNotFound, InsufficientFunds, LimitReached, MissingProperties, WalletNotFound

def register_error_handlers(app):
    @app.errorhandler(ValueError)
    def handle_value_error(e):
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
        return jsonify({
            'message': str(e), 
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