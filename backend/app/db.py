from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

SCHEMA_REVISION = "20260913_mary_help"


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
        # Transaction poolers can reject libpq startup options and move a client
        # between server sessions. Apply query limits per transaction below.
        options["connect_args"] = {"connect_timeout": 5}
        if url.startswith("postgresql+psycopg:"):
            options["connect_args"]["prepare_threshold"] = None
    engine = create_engine(url, **options)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def configure_sqlite(dbapi_connection, _):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()
    elif url.startswith("postgresql"):
        @event.listens_for(engine, "begin")
        def configure_postgresql_transaction(connection):
            # Explicit administrative AUTOCOMMIT has no transaction-local state;
            # application sessions and verification queries use transactions.
            if connection.get_execution_options().get("isolation_level") == "AUTOCOMMIT":
                return
            connection.exec_driver_sql("SET LOCAL statement_timeout = '15s'")
            connection.exec_driver_sql("SET LOCAL lock_timeout = '5s'")
    return engine


def make_sessions(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)
