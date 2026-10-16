"""add broker symbol and executed volume to orders

Revision ID: bbbd2996ea12
Revises: 3735c6f1a310
Create Date: 2026-10-07 16:01:17.855228

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "bbbd2996ea12"
down_revision: str | Sequence[str] | None = "3735c6f1a310"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --------------------------------------------------------------
    # 1. Add broker_symbol temporarily as nullable.
    # --------------------------------------------------------------

    op.add_column(
        "orders",
        sa.Column(
            "broker_symbol",
            sa.String(length=100),
            nullable=True,
        ),
    )

    # --------------------------------------------------------------
    # 2. Add cumulative broker-confirmed executed volume.
    #
    # NULL is intentional for historical orders because AQE does not
    # have authoritative cumulative execution-volume history for them.
    # --------------------------------------------------------------

    op.add_column(
        "orders",
        sa.Column(
            "executed_volume",
            sa.Numeric(10, 2),
            nullable=True,
        ),
    )

    # --------------------------------------------------------------
    # 3. Backfill broker_symbol from account-specific symbol mapping.
    #
    # Canonical:
    #     orders.symbol_id
    #
    # Account-specific broker identity:
    #     account_symbols(account_id, symbol_id)
    #
    # Example:
    #     XAUUSD -> XAUUSD.s
    # --------------------------------------------------------------

    op.execute(sa.text("""
            UPDATE orders AS o
            SET broker_symbol = a.broker_symbol
            FROM account_symbols AS a
            WHERE a.account_id = o.account_id
              AND a.symbol_id = o.symbol_id
              AND a.broker_symbol IS NOT NULL
              AND btrim(a.broker_symbol) <> ''
            """))

    # --------------------------------------------------------------
    # 4. Ensure every existing order was successfully mapped.
    #
    # Never silently substitute the canonical symbol because doing so
    # could make later broker-history reconciliation ambiguous.
    # --------------------------------------------------------------

    connection = op.get_bind()

    unresolved_count = connection.execute(sa.text("""
            SELECT COUNT(*)
            FROM orders
            WHERE broker_symbol IS NULL
               OR btrim(broker_symbol) = ''
            """)).scalar_one()

    if unresolved_count:
        raise RuntimeError(
            "Cannot complete migration: "
            f"{unresolved_count} existing order(s) could not be "
            "mapped to account_symbols.broker_symbol."
        )

    # --------------------------------------------------------------
    # 5. broker_symbol becomes mandatory.
    # --------------------------------------------------------------

    op.alter_column(
        "orders",
        "broker_symbol",
        existing_type=sa.String(length=100),
        nullable=False,
    )

    # --------------------------------------------------------------
    # 6. Index broker identity for account-scoped reconciliation.
    # --------------------------------------------------------------

    op.create_index(
        "ix_orders_account_broker_symbol",
        "orders",
        ["account_id", "broker_symbol"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_orders_account_broker_symbol",
        table_name="orders",
    )

    op.drop_column(
        "orders",
        "executed_volume",
    )

    op.drop_column(
        "orders",
        "broker_symbol",
    )
