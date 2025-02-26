from flask import jsonify
from sqlalchemy.exc import IntegrityError

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