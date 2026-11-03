"""SQLAlchemy engine and session management."""
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


def _make_engine(url: str):
    parsed = make_url(url)
    if parsed.database and parsed.database != ":memory:":
        Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    return engine


engine = _make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    from . import models  # noqa: F401  (registers tables on Base)
    from .upgrades import add_missing_columns, apply_type_rules_to_all, fold_os_nodes, merge_password_totp_edges

    Base.metadata.create_all(engine)
    add_missing_columns(engine)
    with SessionLocal() as session:
        fold_os_nodes(session)
        apply_type_rules_to_all(session)
        merge_password_totp_edges(session)


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
