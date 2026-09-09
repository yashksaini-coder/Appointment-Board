import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://appointments:appointments@localhost:5432/appointments",
)


def _with_driver(url: str) -> str:
    """Managed databases hand out `postgres://` or `postgresql://` URLs.

    SQLAlchemy maps both to psycopg2, which this project does not install, so
    the app would die at boot with ModuleNotFoundError. Point them at psycopg 3.
    """
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


engine = create_engine(
    _with_driver(DATABASE_URL),
    pool_pre_ping=True,
    # Total connections = workers x (pool_size + max_overflow). Keep that under
    # the server's max_connections; managed instances are often 20-100.
    pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
