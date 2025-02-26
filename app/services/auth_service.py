from flask_jwt_extended import create_access_token
from sqlalchemy.exc import IntegrityError

from app.custom_exceptions import AlreadyExists, MissingProperties
from ..models.user import User
from ..models.wallet import Wallet, WalletCurrencyType
from ..models.revokedtoken import RevokedToken
from .. import db

class AuthService:    
    def generate_token(self,user):
        try:
            additional_claims = {
                'first_name':user.first_name, 
                'last_name':user.last_name, 
                'email':user.email, 
                'role':user.role
            }
            access_token = create_access_token(
                identity=str(user.id), 
                additional_claims= additional_claims)
            return access_token
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"An unexpected error occured: {str(e)}")
    
    def create_user(self, first_name, last_name, email, password):
        # Check if email already exists
        try:
            if not first_name or not last_name or not email or not password:
                raise MissingProperties("Could not create user as certain properties are missing")
            existing_user = User.query.filter_by(email= email).first()
            if existing_user:
                raise AlreadyExists("A user with this email already exists")
            # Create user
            new_user = User(
                first_name = first_name,
                last_name = last_name,
                email = email,
            )
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            # Create wallet after User is saved
            wallet = Wallet(user_id = new_user.id, currency=WalletCurrencyType.USD)
            db.session.add(wallet)
            db.session.commit()
            
            # Refresh the user to load the wallet relationship
            db.session.refresh(new_user)
            return new_user
        except MissingProperties:
            db.session.rollback()
            raise
        except AlreadyExists:
            db.session.rollback()
            raise
        except IntegrityError:
            db.session.rollback()
            raise
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"An unexpected error occured: {str(e)}")
    
    def admin_signup(self, first_name, last_name, email, password):
        try:
            existing_user = User.query.filter_by(email= email).first()
            if existing_user:
                raise AlreadyExists("A user with this email already exists")
            new_user = User(
                first_name = first_name,
                last_name = last_name,
                email = email,
                role="admin"
            )
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            db.session.expire_all()
            return new_user.to_dict()
        
        except AlreadyExists:
            db.session.rollback()
            raise
        except IntegrityError:
            db.session.rollback()
            raise
        
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"An unexpected error occured: {str(e)}")
    
    def authenticate_user(self, email, password):
        try:
            user = User.query.filter_by(email=email).first()
            if user and user.check_password(password):
                return user
            return None
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"An unexpected error occured: {str(e)}")
    
    def reset_password(self, user_id, data):
        try:
            user = User.query.get(user_id)
            if user and user.check_password(data['old_password']):
                user.set_password(data['new_password'])
                db.session.commit()
                return user.to_dict()
            return None
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"An unexpected error occured: {str(e)}")        
    
    def logout(self, jti):
        try:
            RevokedToken.revoke(jti)
            return True
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"An unexpected error occured: {str(e)}")
