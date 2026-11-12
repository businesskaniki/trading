"""Store MT5 broker identifiers as BIGINT."""

from alembic import op
import sqlalchemy as sa


revision = "a91f2d6c7e40"
down_revision = "5cde44738d42"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "positions",
        "ticket",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=False,
        postgresql_using="ticket::bigint",
    )

    op.alter_column(
        "trades",
        "ticket",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=False,
        postgresql_using="ticket::bigint",
    )

    for column in (
        "broker_order_id",
        "broker_deal_id",
        "broker_position_id",
    ):
        op.alter_column(
            "orders",
            column,
            existing_type=sa.Integer(),
            type_=sa.BigInteger(),
            existing_nullable=True,
            postgresql_using=f"{column}::bigint",
        )


def downgrade() -> None:
    # This downgrade intentionally fails if any identifier is outside
    # the INTEGER range rather than truncating or corrupting values.
    for column in (
        "broker_position_id",
        "broker_deal_id",
        "broker_order_id",
    ):
        op.alter_column(
            "orders",
            column,
            existing_type=sa.BigInteger(),
            type_=sa.Integer(),
            existing_nullable=True,
            postgresql_using=f"{column}::integer",
        )

    op.alter_column(
        "trades",
        "ticket",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=False,
        postgresql_using="ticket::integer",
    )

    op.alter_column(
        "positions",
        "ticket",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=False,
        postgresql_using="ticket::integer",
    )
