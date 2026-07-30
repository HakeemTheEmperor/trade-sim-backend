import logging

from flask_jwt_extended import create_access_token
from sqlalchemy.exc import IntegrityError

from app.custom_exceptions import AlreadyExists, MissingProperties
from ..models.user import User, UserRoles
from ..models.wallet import Wallet, WalletCurrencyType
from ..models.revokedtoken import RevokedToken
from ..models.email_otp import EmailVerificationCode
from .email_service import EmailService
from .. import db

logger = logging.getLogger(__name__)

class AuthService:
    def generate_token(self,user):
        try:
            additional_claims = {
                'first_name':user.first_name, 
                'last_name':user.last_name, 
                'email':user.email,
                'role':user.role.value,
                # Always True in practice — a token is only ever minted for a
                # verified user — but carried so /me can answer without a DB hit.
                'is_verified':user.is_verified
            }
            access_token = create_access_token(
                identity=str(user.id), 
                additional_claims= additional_claims)
            return access_token
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"An unexpected error occured: {str(e)}")
    
    def create_user(self, first_name, last_name, email, password, username):
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
                username=username,
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

            # The account exists but is inert until verified: no session is
            # issued (see the signup route) and /signin refuses. Delivery
            # failure is logged, not raised — the user can hit "Resend code"
            # rather than lose an account that's already committed.
            self.send_verification_code(new_user)

            return new_user
        except MissingProperties:
            db.session.rollback()
            raise
        except AlreadyExists:
            db.session.rollback()
            raise
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"An unexpected error occured: {str(e)}")
    
    def admin_signup(self, first_name, last_name, email, password, username):
        try:
            existing_user = User.query.filter_by(email= email).first()
            if existing_user:
                raise AlreadyExists("A user with this email already exists")
            existing_username = User.query.filter_by(username=username).first()
            if existing_username:
                raise AlreadyExists("A user with this username already exists")
            new_user = User(
                first_name = first_name,
                last_name = last_name,
                username = username,
                email = email,
                role=UserRoles.ADMIN,
                # Admins are created by an authenticated super-admin, not by
                # someone claiming an address, so there's nothing to prove.
                is_verified=True
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
    
    def send_verification_code(self, user):
        """Issue a fresh OTP and email it. Returns True if it went out.

        Issuing and sending are deliberately coupled: a code that was generated
        but never delivered is worse than no code, because it invalidates the
        previous one (see EmailVerificationCode.issue) and strands the user.
        """
        try:
            code = EmailVerificationCode.issue(user)
            return EmailService().send_verification_code(user, code)
        except Exception:
            db.session.rollback()
            logger.exception("Failed to issue verification code for user %s", user.id)
            return False

    def verify_email(self, email, code):
        """Activate the account behind ``email`` if ``code`` is its live OTP.

        Returns (user, newly_verified). Re-verifying an already-verified account
        is a no-op success rather than an error: a double-submitted form or a
        back-button retry shouldn't read as a failure to the user.

        Raises ValueError on a bad/expired code, which the registered handler
        renders as a clean 400. The message is intentionally the same for a
        wrong code, an expired code, an exhausted one, and an unknown email —
        it must not become an account-existence oracle, since this endpoint
        needs no password.
        """
        try:
            invalid = ValueError("Invalid or expired code. Request a new one and try again.")
            if not email or not code:
                raise invalid

            user = User.query.filter_by(email=email).first()
            if user is None:
                raise invalid
            if user.is_verified:
                return user, False

            if not EmailVerificationCode.verify(user, code):
                raise invalid

            user.is_verified = True
            db.session.commit()
            return user, True
        except ValueError:
            db.session.rollback()
            raise
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"An unexpected error occured: {str(e)}")

    def resend_verification(self, email):
        """Re-send an OTP, silently doing nothing when that isn't appropriate.

        Returns None either way. The caller must respond identically regardless,
        so this endpoint can't be used to test which addresses are registered or
        which are still unverified. Unknown address, already verified, and
        still-in-cooldown are all indistinguishable from the outside.
        """
        try:
            if not email:
                return
            user = User.query.filter_by(email=email).first()
            if user is None or user.is_verified:
                return
            if EmailVerificationCode.seconds_until_resend_allowed(user) > 0:
                logger.info("Resend for user %s suppressed by cooldown", user.id)
                return
            self.send_verification_code(user)
        except Exception:
            db.session.rollback()
            logger.exception("Resend verification failed for %r", email)

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
