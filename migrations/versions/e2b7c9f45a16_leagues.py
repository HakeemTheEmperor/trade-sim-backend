"""leagues and memberships

Revision ID: e2b7c9f45a16
Revises: d9f4a1c2e830
Create Date: 2026-08-01 15:22:40.113905

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e2b7c9f45a16'
down_revision = 'd9f4a1c2e830'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'leagues',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=60), nullable=False),
        sa.Column('join_code', sa.String(length=16), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.current_timestamp(), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        # The code is the only thing gating entry, so it has to be unique.
        sa.UniqueConstraint('join_code', name='uq_league_join_code'),
    )
    with op.batch_alter_table('leagues', schema=None) as batch_op:
        batch_op.create_index('ix_league_join_code', ['join_code'], unique=False)

    op.create_table(
        'league_memberships',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('league_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('joined_at', sa.DateTime(timezone=True),
                  server_default=sa.func.current_timestamp(), nullable=False),
        sa.ForeignKeyConstraint(['league_id'], ['leagues.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        # Joining twice would double a member in the standings.
        sa.UniqueConstraint('league_id', 'user_id', name='uq_league_member'),
    )
    with op.batch_alter_table('league_memberships', schema=None) as batch_op:
        batch_op.create_index('ix_league_membership_user', ['user_id'], unique=False)
        batch_op.create_index('ix_league_membership_league', ['league_id'], unique=False)


def downgrade():
    with op.batch_alter_table('league_memberships', schema=None) as batch_op:
        batch_op.drop_index('ix_league_membership_league')
        batch_op.drop_index('ix_league_membership_user')
    op.drop_table('league_memberships')

    with op.batch_alter_table('leagues', schema=None) as batch_op:
        batch_op.drop_index('ix_league_join_code')
    op.drop_table('leagues')
