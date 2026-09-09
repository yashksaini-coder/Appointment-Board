"""Tests run against a real PostgreSQL database.

The overlap guard is an exclusion constraint, so SQLite would not exercise the
thing most worth testing. conftest carves out a sibling `_test` database on the
same server and truncates it between tests.
"""
import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://appointments:appointments@localhost:5432/appointments",
)
TEST_URL = make_url(BASE_URL).set(database=make_url(BASE_URL).database + "_test")

admin = create_engine(make_url(BASE_URL).set(database="postgres"), isolation_level="AUTOCOMMIT")
with admin.connect() as conn:
    exists = conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": TEST_URL.database})
    if not exists:
        conn.execute(text(f'CREATE DATABASE "{TEST_URL.database}"'))
admin.dispose()

os.environ["DATABASE_URL"] = TEST_URL.render_as_string(hide_password=False)

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

Base.metadata.create_all(engine)


@pytest.fixture()
def client():
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE appointments RESTART IDENTITY"))
    # Deliberately NOT `with TestClient(app)`: entering it runs the lifespan,
    # which would seed sample rows straight back into the table we just cleared.
    return TestClient(app)
