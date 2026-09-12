"""Optional real-PostgreSQL regression for transaction-pooler-safe timeouts."""
import os

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.db import make_engine


def test_limits_reapply_after_commit_and_rollback():
    url = os.getenv("NCDAI_DATABASE_TEST_URL")
    if not url:
        pytest.skip("Dedicated PostgreSQL test database not configured")
    target = make_url(url)
    assert target.host in {"127.0.0.1", "localhost"}
    assert target.database in {"ncdai2_test", "ncdai_ci_checks"}
    engine = make_engine(url)
    try:
        with engine.connect() as connection:
            assert connection.connection.driver_connection.prepare_threshold is None

            def bounded():
                assert connection.scalar(text("SHOW statement_timeout")) == "15s"
                assert connection.scalar(text("SHOW lock_timeout")) == "5s"

            bounded()
            connection.execute(text("SET LOCAL statement_timeout = '90ms'"))
            connection.execute(text("SET LOCAL lock_timeout = '40ms'"))
            assert connection.scalar(text("SHOW statement_timeout")) == "90ms"
            connection.commit()
            bounded()
            connection.execute(text("SET LOCAL statement_timeout = '80ms'"))
            connection.rollback()
            bounded()
            connection.rollback()
        # Administrative autocommit must remain usable without issuing SET LOCAL
        # outside a transaction. Application sessions never use this mode.
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            assert connection.scalar(text("SELECT 1")) == 1
    finally:
        engine.dispose()
