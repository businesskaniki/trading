"""create risk profiles table

Revision ID: 7a35f1668f86
Revises: 39d76528d819
Create Date: 2026-08-24 17:11:35.635611

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7a35f1668f86"
down_revision: Union[str, Sequence[str], None] = "39d76528d819"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    op.create_table(
        "risk_profiles",

        sa.Column(
            "account_id",
            sa.UUID(),
            nullable=False,
        ),

        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),

        sa.Column(
            "base_risk_percent",
            sa.Numeric(8, 4),
            nullable=False,
            server_default="1.0000",
        ),

        sa.Column(
            "min_risk_percent",
            sa.Numeric(8, 4),
            nullable=False,
            server_default="0.2500",
        ),

        sa.Column(
            "max_risk_percent",
            sa.Numeric(8, 4),
            nullable=False,
            server_default="2.0000",
        ),

        sa.Column(
            "risk_multiplier",
            sa.Numeric(8, 4),
            nullable=False,
            server_default="1.0000",
        ),

        sa.Column(
            "max_daily_loss_percent",
            sa.Numeric(8, 4),
            nullable=False,
            server_default="3.0000",
        ),

        sa.Column(
            "max_drawdown_percent",
            sa.Numeric(8, 4),
            nullable=False,
            server_default="10.0000",
        ),

        sa.Column(
            "max_open_risk_percent",
            sa.Numeric(8, 4),
            nullable=False,
            server_default="5.0000",
        ),

        sa.Column(
            "max_positions",
            sa.Integer(),
            nullable=False,
            server_default="10",
        ),

        sa.Column(
            "max_symbol_exposure_percent",
            sa.Numeric(8, 4),
            nullable=False,
            server_default="5.0000",
        ),

        sa.Column(
            "max_strategy_exposure_percent",
            sa.Numeric(8, 4),
            nullable=False,
            server_default="5.0000",
        ),

        sa.Column(
            "hard_limits_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),

        sa.Column(
            "id",
            sa.UUID(),
            nullable=False,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),

        sa.ForeignKeyConstraint(
            ["account_id"],
            ["trading_accounts.id"],
            ondelete="CASCADE",
        ),

        sa.PrimaryKeyConstraint(
            "id",
        ),

        sa.UniqueConstraint(
            "account_id",
            name="uq_risk_profiles_account_id",
        ),
    )


def downgrade() -> None:

    op.drop_table(
        "risk_profiles"
    )