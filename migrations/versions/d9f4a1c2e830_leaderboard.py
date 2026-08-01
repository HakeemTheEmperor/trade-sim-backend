"""leaderboard: seasons, participants, equity snapshots

Revision ID: d9f4a1c2e830
Revises: c5e18d40b7a2
Create Date: 2026-08-01 11:37:02.884210

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd9f4a1c2e830'
down_revision = 'c5e18d40b7a2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'seasons',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ends_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.current_timestamp(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('seasons', schema=None) as batch_op:
        batch_op.create_index('ix_season_window', ['starts_at', 'ends_at'], unique=False)

    op.create_table(
        'season_participants',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('season_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('baseline_equity', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.current_timestamp(), nullable=False),
        sa.ForeignKeyConstraint(['season_id'], ['seasons.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        # A user is enrolled once per season. This is also what enforces the
        # mid-season-joiner rule: no row means not ranked.
        sa.UniqueConstraint('season_id', 'user_id', name='uq_season_participant'),
    )
    with op.batch_alter_table('season_participants', schema=None) as batch_op:
        batch_op.create_index('ix_season_participant_season', ['season_id'], unique=False)

    op.create_table(
        'equity_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('captured_on', sa.Date(), nullable=False),
        sa.Column('equity', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('cash', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('holdings', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.current_timestamp(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        # Makes the daily job idempotent: a retry updates rather than duplicates.
        sa.UniqueConstraint('user_id', 'captured_on', name='uq_equity_snapshot_day'),
    )
    with op.batch_alter_table('equity_snapshots', schema=None) as batch_op:
        batch_op.create_index('ix_equity_snapshot_user_day', ['user_id', 'captured_on'], unique=False)


def downgrade():
    with op.batch_alter_table('equity_snapshots', schema=None) as batch_op:
        batch_op.drop_index('ix_equity_snapshot_user_day')
    op.drop_table('equity_snapshots')

    with op.batch_alter_table('season_participants', schema=None) as batch_op:
        batch_op.drop_index('ix_season_participant_season')
    op.drop_table('season_participants')

    with op.batch_alter_table('seasons', schema=None) as batch_op:
        batch_op.drop_index('ix_season_window')
    op.drop_table('seasons')
