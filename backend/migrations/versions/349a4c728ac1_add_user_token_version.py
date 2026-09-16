"""add user token version

Revision ID: 349a4c728ac1
Revises: 214a13c83b04
"""

from alembic import op
import sqlalchemy as sa


revision = "349a4c728ac1"
down_revision = "214a13c83b04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("users", "token_version", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "token_version")
