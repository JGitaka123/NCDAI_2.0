from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

SCHEMA_REVISION = "20260912_guards"


class Base(DeclarativeBase):
    pass


def make_engine(url: str):
    options = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False, "timeout": 30}
        if url in {"sqlite://", "sqlite:///:memory:"}:
            options["poolclass"] = StaticPool
    elif url.startswith("postgresql"):
        options.update(pool_size=2, max_overflow=0, pool_timeout=5, pool_recycle=300)
        # Bound network connection, query execution and lock waits so a database
        # outage or blocked transaction cannot indefinitely occupy an API worker.
        options["connect_args"] = {
            "connect_timeout": 5,
            "options": "-c statement_timeout=15000 -c lock_timeout=5000",
        }
    engine = create_engine(url, **options)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def configure_sqlite(dbapi_connection, _):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()
    return engine


def make_sessions(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)
