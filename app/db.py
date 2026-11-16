"""Database layer: SQLAlchemy models + engine, works with MySQL or SQLite.

Backend is chosen entirely by DATABASE_URL, e.g.:
  mysql+pymysql://user:pass@host:3306/transcryber   (MySQL)
  sqlite:////app/data/transcryber.db                 (SQLite)
"""

import logging
import time
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
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
    duration = Column(Float)
    text = Column(Text)
    segments = Column(Text)  # JSON-encoded list of segment dicts

    user = relationship("User", back_populates="transcripts")


def init_db(retries: int = 30, delay: float = 3.0) -> None:
    """Create tables, retrying so the app can wait for MySQL to come up."""
    last_err = None
    safe_url = engine.url.render_as_string(hide_password=True)
    for attempt in range(1, retries + 1):
        try:
            Base.metadata.create_all(engine)
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
