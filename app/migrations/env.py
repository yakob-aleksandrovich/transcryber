"""Alembic environment for Transcryber.

Migrations normally run automatically at app startup (see app/db.py:init_db),
which passes an open connection in via ``config.attributes["connection"]``.
Run from the command line (e.g. ``alembic revision --autogenerate``), it uses
the app's own engine, so the database comes from config.yaml as usual.
"""

from alembic import context

from app.db import Base, engine

target_metadata = Base.metadata


def _configure_and_run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # SQLite can't ALTER most things in place; batch mode copies the table.
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = context.config.attributes.get("connection")
    if connection is not None:
        _configure_and_run(connection)
        return
    with engine.connect() as conn:
        _configure_and_run(conn)


if context.is_offline_mode():
    raise SystemExit("Offline (--sql) mode is not supported; run against a database.")
run_migrations_online()
