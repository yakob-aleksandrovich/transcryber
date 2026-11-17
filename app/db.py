"""Database layer: SQLAlchemy models + engine, works with MySQL or SQLite.

Backend is chosen entirely by DATABASE_URL, e.g.:
  mysql+pymysql://user:pass@host:3306/transcryber   (MySQL)
  sqlite:////app/data/transcryber.db                 (SQLite)

The schema is managed by Alembic migrations in app/migrations/, applied
automatically at startup by init_db(). After changing a model here, add a
migration (see docs/development.md).
"""

import logging
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    inspect,
)
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from .config import DATABASE_URL

logger = logging.getLogger("transcryber.db")

_connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    # SQLite + our background worker thread need this.
    _connect_args = {"check_same_thread": False}

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,          # recover from dropped MySQL connections
    connect_args=_connect_args,
    future=True,
)
SessionLocal = sessionmaker(
    bind=engine, autoflush=False, expire_on_commit=False, future=True
)

Base = declarative_base()

# Long text. On MySQL/MariaDB plain TEXT holds only 64 KB, too small for the
# transcript of a long recording, so use MEDIUMTEXT (16 MB) there. Other
# databases (SQLite) have no such limit and keep TEXT. See migration 0003.
LongText = Text().with_variant(MEDIUMTEXT(), "mysql", "mariadb")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    transcripts = relationship(
        "Transcript", back_populates="user", cascade="all, delete-orphan"
    )


class Transcript(Base):
    __tablename__ = "transcripts"

    id = Column(String(32), primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    original_name = Column(String(512))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    language = Column(String(32))
    duration = Column(Float)  # length of the audio, in seconds
    # Wall-clock seconds from start of processing to transcript ready (includes
    # model load on the first job). NULL for transcripts made before 0002.
    processing_seconds = Column(Float)
    text = Column(LongText)
    segments = Column(LongText)  # JSON-encoded list of segment dicts

    user = relationship("User", back_populates="transcripts")


MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
# The first migration: the schema that create_all() used to build. Databases
# from before migrations existed already have it, so they are stamped, not run.
BASELINE_REVISION = "0001"


def _migrate() -> None:
    """Bring the database schema up to date (new, old or pre-migration DBs)."""
    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        tables = set(inspect(conn).get_table_names())
        if "alembic_version" not in tables and "users" in tables:
            logger.info(
                "Existing database without migration history; marking it as "
                "baseline revision %s.", BASELINE_REVISION
            )
            command.stamp(cfg, BASELINE_REVISION)
        command.upgrade(cfg, "head")


def init_db(retries: int = 30, delay: float = 3.0) -> None:
    """Apply migrations, retrying so the app can wait for MySQL to come up."""
    last_err = None
    safe_url = engine.url.render_as_string(hide_password=True)
    for attempt in range(1, retries + 1):
        try:
            _migrate()
            logger.info("Database ready (%s).", safe_url)
            return
        except OperationalError as err:
            last_err = err
            logger.warning(
                "Database not ready yet (attempt %d/%d): %s", attempt, retries, err
            )
            time.sleep(delay)
    logger.error("Database unavailable after %d attempts (%s).", retries, safe_url)
    raise last_err
