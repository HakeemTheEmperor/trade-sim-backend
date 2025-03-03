from .. import db  # Import db instance
from datetime import datetime

class RevokedToken(db.Model):
    __tablename__ = "revoked_tokens"
    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(36), unique=True, nullable=False)  # Unique token identifier
    created_at = db.Column(db.DateTime(timezone=True), default=db.func.current_timestamp(), nullable=False)

    @classmethod
    def is_revoked(cls, jti):
        """Check if the token is revoked"""
        return db.session.query(cls.id).filter_by(jti=jti).first() is not None

    @classmethod
    def revoke(cls, jti):
        """Add token to blacklist"""
        revoked_token = cls(jti=jti)
        db.session.add(revoked_token)
        db.session.commit()
