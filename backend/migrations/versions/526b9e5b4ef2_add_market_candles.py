"""add persisted market candles

Revision ID: 526b9e5b4ef2
Revises: 349a4c728ac1
"""
from alembic import op
import sqlalchemy as sa

revision = "526b9e5b4ef2"
down_revision = "349a4c728ac1"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("market_candles", sa.Column("symbol", sa.String(64), nullable=False), sa.Column("timeframe", sa.String(8), nullable=False), sa.Column("timestamp", sa.BigInteger(), nullable=False), sa.Column("open", sa.Float(), nullable=False), sa.Column("high", sa.Float(), nullable=False), sa.Column("low", sa.Float(), nullable=False), sa.Column("close", sa.Float(), nullable=False), sa.Column("volume", sa.BigInteger(), nullable=False), sa.Column("spread", sa.BigInteger(), nullable=False), sa.Column("id", sa.UUID(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("symbol", "timeframe", "timestamp", name="uq_market_candle"))
    op.create_index("ix_market_candles_lookup", "market_candles", ["symbol", "timeframe", "timestamp"])

def downgrade() -> None:
    op.drop_index("ix_market_candles_lookup", table_name="market_candles")
    op.drop_table("market_candles")
