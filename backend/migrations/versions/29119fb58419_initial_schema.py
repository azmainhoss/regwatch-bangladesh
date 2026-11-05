"""initial_schema

Revision ID: 29119fb58419
Revises: 
Create Date: 2026-11-05 19:53:54.523544

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '29119fb58419'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure all foundational base tables are created if initializing from scratch
    bind = op.get_bind()
    from backend.app.database.models import Base
    Base.metadata.create_all(bind)


def downgrade() -> None:
    pass
