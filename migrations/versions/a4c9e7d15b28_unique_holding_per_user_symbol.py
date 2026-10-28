"""one holding per (user_id, symbol)

Trades now add to a position with INSERT ... ON CONFLICT, which needs a unique
constraint on (user_id, symbol). The table never had one, so concurrent first
buys could create two rows for the same position.

Any existing duplicates are merged first (quantities summed into the oldest row,
the rest deleted), or the constraint could not be created. No shares are lost:
the merged row holds the total, and the transactions ledger is untouched.

The unique constraint's index leads with user_id, so it replaces the plain
(user_id, symbol) index added in the previous migration.

Revision ID: a4c9e7d15b28
Revises: f3a8d2c61b94
Create Date: 2026-10-28 14:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'a4c9e7d15b28'
down_revision = 'f3a8d2c61b94'
branch_labels = None
depends_on = None


def upgrade():
    # Fold each duplicated position's quantity into its oldest row...
    op.execute("""
        UPDATE users_stock_wallet
        SET quantity = (
            SELECT SUM(q.quantity) FROM users_stock_wallet q
            WHERE q.user_id = users_stock_wallet.user_id AND q.symbol = users_stock_wallet.symbol
        )
        WHERE id IN (
            SELECT MIN(id) FROM users_stock_wallet
            GROUP BY user_id, symbol HAVING COUNT(*) > 1
        )
    """)
    # ...then drop the rest.
    op.execute("""
        DELETE FROM users_stock_wallet
        WHERE id NOT IN (SELECT MIN(id) FROM users_stock_wallet GROUP BY user_id, symbol)
    """)
    with op.batch_alter_table('users_stock_wallet', schema=None) as batch_op:
        batch_op.drop_index('ix_users_stock_wallet_user_symbol')
        batch_op.create_unique_constraint('uq_users_stock_wallet_user_symbol', ['user_id', 'symbol'])


def downgrade():
    # Merged duplicates are not split back apart; the totals are correct as is.
    with op.batch_alter_table('users_stock_wallet', schema=None) as batch_op:
        batch_op.drop_constraint('uq_users_stock_wallet_user_symbol', type_='unique')
        batch_op.create_index('ix_users_stock_wallet_user_symbol', ['user_id', 'symbol'], unique=False)
