from app.custom_exceptions import DataNotFound
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