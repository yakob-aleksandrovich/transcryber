"""use MEDIUMTEXT for transcript text on MySQL

On MySQL/MariaDB, TEXT holds at most 64 KB, so saving the transcript of a long
recording (about an hour of speech) failed with "Data too long for column".
This changes transcripts.text and transcripts.segments to MEDIUMTEXT (16 MB).
Other databases (SQLite) have no such limit; there this migration does nothing.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNS = ("text", "segments")


def _is_mysql() -> bool:
    return op.get_bind().dialect.name in ("mysql", "mariadb")


def upgrade() -> None:
    """Upgrade schema."""
    if not _is_mysql():
        return
    for col in COLUMNS:
        op.alter_column(
            "transcripts", col,
            existing_type=sa.Text(), type_=mysql.MEDIUMTEXT(), existing_nullable=True,
        )


def downgrade() -> None:
    """Downgrade schema.

    Fails if any row holds more than 64 KB in these columns.
    """
    if not _is_mysql():
        return
    for col in COLUMNS:
        op.alter_column(
            "transcripts", col,
            existing_type=mysql.MEDIUMTEXT(), type_=sa.Text(), existing_nullable=True,
        )
