"""transaction fee column

Revision ID: c5e18d40b7a2
Revises: a7c31f5be204
Create Date: 2026-08-01 10:04:51.220914

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c5e18d40b7a2'
down_revision = 'a7c31f5be204'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        # server_default 0 so the historical rows — every trade made before
        # costs existed — read as free rather than NULL. They genuinely were.
        batch_op.add_column(sa.Column(
            'fee', sa.Numeric(precision=18, scale=4), nullable=False, server_default='0'
        ))


def downgrade():
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.drop_column('fee')
