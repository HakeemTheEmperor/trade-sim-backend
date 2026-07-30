"""email verification (is_verified + otp codes)

Revision ID: a7c31f5be204
Revises: 34802fe132da
Create Date: 2026-07-30 09:12:44.128301

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7c31f5be204'
down_revision = '34802fe132da'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        # server_default=false, NOT true. The one-off UPDATE below grandfathers
        # the accounts that exist right now; every row inserted afterwards must
        # start unverified. Defaulting the column to true would silently verify
        # all future signups and quietly disable the whole feature.
        batch_op.add_column(sa.Column(
            'is_verified', sa.Boolean(), nullable=False, server_default=sa.false()
        ))

    # Existing users signed up before verification existed and were never asked
    # for a code. Leaving them at false would lock every current user out on
    # their next sign-in, and some may have registered with an address they can
    # no longer receive mail at.
    op.execute("UPDATE users SET is_verified = true")

    op.create_table(
        'email_verification_codes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('code_hash', sa.String(length=255), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.current_timestamp(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('email_verification_codes', schema=None) as batch_op:
        # Every lookup is "newest code for this user" — see
        # EmailVerificationCode._latest.
        batch_op.create_index('ix_email_otp_user_created', ['user_id', 'created_at'], unique=False)


def downgrade():
    with op.batch_alter_table('email_verification_codes', schema=None) as batch_op:
        batch_op.drop_index('ix_email_otp_user_created')

    op.drop_table('email_verification_codes')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('is_verified')
