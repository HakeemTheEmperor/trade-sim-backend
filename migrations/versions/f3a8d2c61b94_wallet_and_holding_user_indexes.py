"""index wallets.user_id and users_stock_wallet(user_id, symbol)

Postgres does not index foreign keys on its own, so every "this user's wallets"
and "this user's holdings" lookup was a sequential scan of the whole table. That
is the hot path of the leaderboard and league tables, and of every trade.

The holdings index leads with user_id, so it serves user-only lookups as well as
the (user_id, symbol) lookups trades and quantity checks do.

Revision ID: f3a8d2c61b94
Revises: e2b7c9f45a16
Create Date: 2026-10-28 10:30:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'f3a8d2c61b94'
down_revision = 'e2b7c9f45a16'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('wallets', schema=None) as batch_op:
        batch_op.create_index('ix_wallets_user_id', ['user_id'], unique=False)
    with op.batch_alter_table('users_stock_wallet', schema=None) as batch_op:
        batch_op.create_index('ix_users_stock_wallet_user_symbol', ['user_id', 'symbol'], unique=False)


def downgrade():
    with op.batch_alter_table('users_stock_wallet', schema=None) as batch_op:
        batch_op.drop_index('ix_users_stock_wallet_user_symbol')
    with op.batch_alter_table('wallets', schema=None) as batch_op:
        batch_op.drop_index('ix_wallets_user_id')
