"""SQLAlchemy engine + WAL setup + Session factory."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from thermofft.storage.models import Base


_ENGINES: dict[str, Engine] = {}


def _enable_wal(dbapi_conn, _connection_record) -> None:
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


def get_engine(db_path: str | Path) -> Engine:
    """Получить (создать-кэшировать) SQLAlchemy engine для SQLite."""
    key = str(Path(db_path).resolve())
    if key in _ENGINES:
        return _ENGINES[key]
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{key}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    event.listen(engine, "connect", _enable_wal)
    _ENGINES[key] = engine
    return engine


def init_db(db_path: str | Path) -> Engine:
    """Создать все таблицы (idempotent)."""
    engine = get_engine(db_path)
    Base.metadata.create_all(engine)
    return engine


def make_session_factory(db_path: str | Path) -> sessionmaker[Session]:
    engine = get_engine(db_path)
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope(db_path: str | Path) -> Iterator[Session]:
    Session_ = make_session_factory(db_path)
    sess = Session_()
    try:
        yield sess
        sess.commit()
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()
