from sqlite3 import ProgrammingError
from app.custom_exceptions import DataNotFound, MissingProperties
from app.models.user import User
from app.models.user_stock_wallet import UserStockWallet
from .. import db

class UserService:
    def get_all_users(self):
        try:
            users = User.query.all()
            return [user.to_dict() for user in users]
        except Exception as e:
            raise RuntimeError(f"An Unexpected error occured: {str(e)}")
        
    def get_user_by_id(self, user_id):
        try:
            user = User.query.get(user_id)
            if not user:
                raise DataNotFound("User not found")
            else:
                return user.to_dict()
        except DataNotFound:
            raise
        except Exception as e:
            raise RuntimeError(f"An Unexpected error occured: {str(e)}")
    
    def update_user_data(self, user_id, data):
        try:
            editable_fields = ["username", "first_name", "last_name", "phone_number"]

            # Validate & clean data (only includes valid fields)
            cleaned_data = self.validate_and_clean_data(data, editable_fields)

            # Fetch user from database
            user = User.query.get(user_id)
            if not user:
                raise DataNotFound("User not found")

            # Update only the provided fields
            for field, value in cleaned_data.items():
                setattr(user, field, value)

            # Commit changes
            db.session.commit()

            return {
                "message": "User updated successfully",
                "updated_fields": list(cleaned_data.keys()),  # Show only updated fields
                "user": user.to_dict()
            }

        except MissingProperties as e:
            return {"error": str(e)}, 400
        except DataNotFound as e:
            return {"error": str(e)}, 404
        except Exception as e:
            db.session.rollback()  # Rollback in case of failure
            return {"error": f"An unexpected error occurred: {str(e)}"}, 500
        
    def validate_and_clean_data(self, data, required_fields):
        try:
            if not data:
                raise MissingProperties("No data provided for update")

            # Filter only the valid fields and ensure they are not empty
            cleaned_data = {
                key: value.strip() for key, value in data.items()
                if key in required_fields and isinstance(value, str) and value.strip()
            }

            if not cleaned_data:
                raise MissingProperties("No valid fields provided for update")

            return cleaned_data

        except MissingProperties:
            raise
        except Exception as e:
            raise RuntimeError(f"An Unexpected error occurred: {str(e)}")