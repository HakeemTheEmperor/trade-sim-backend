from flask import jsonify
from sqlalchemy.exc import IntegrityError
from .custom_exceptions import AlreadyExists, DataNotFound, InsufficientFunds, MissingProperties, WalletNotFound

def register_error_handlers(app):
    @app.errorhandler(ValueError)
    def handle_value_error(e):
        return jsonify({'error': str(e)}), 400
    
    @app.errorhandler(IntegrityError)
    def handle_integrity_error(e):
        return jsonify({'error': 'Database error, please try again'}), 500

    @app.errorhandler(RuntimeError)
    def handle_runtime_error(e):
        return jsonify({'error': str(e)}), 500
    
    @app.errorhandler(KeyError)
    def handle_key_error(e):
        return jsonify({'error': 'Invalid request'}), 400
    
    @app.errorhandler(MissingProperties)
    def handle_missing_properties_error(e):
        return jsonify({
            'error': str(e)
        }), 400
        
    @app.errorhandler(WalletNotFound)
    def handle_wallet_not_found_error(e):
        return jsonify({
            'error': str(e)
        }), 404
    
    @app.errorhandler(AlreadyExists)
    def handle_already_exists(e):
        return jsonify({
            'error': str(e)
        }), 409
    
    @app.errorhandler(DataNotFound)
    def handle_data_not_found(e):
        return jsonify({
            'error': str(e)
        }), 404
    
    @app.errorhandler(InsufficientFunds)
    def handle_insufficient_funds(e):
        return jsonify({
            'error': str(e)
        }), 402