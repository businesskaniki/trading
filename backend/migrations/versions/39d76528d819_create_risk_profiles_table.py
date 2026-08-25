"""create risk profiles table

Revision ID: 39d76528d819
Revises: a3b5c3eb862e
Create Date: 2026-08-24 17:09:14.775554

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '39d76528d819'
down_revision: Union[str, Sequence[str], None] = 'a3b5c3eb862e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
