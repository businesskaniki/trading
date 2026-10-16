"""allow positions without AQE orders

Revision ID: b3eec82b1a6d
Revises: bbbd2996ea12
Create Date: 2026-10-11 18:40:55.267852

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3eec82b1a6d'
down_revision: Union[str, Sequence[str], None] = 'bbbd2996ea12'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
