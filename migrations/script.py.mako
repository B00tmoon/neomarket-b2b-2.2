"""Generic migration template."""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'head'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
