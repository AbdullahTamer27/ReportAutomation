"""SQLAlchemy engine, session factory, and Base for the web app."""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from .config import DATABASE_URL, DATA_DIR

# Ensure the data dir exists before SQLite tries to create the file.
os.makedirs(DATA_DIR, exist_ok=True)

# check_same_thread=False so the SQLite connection can be used across FastAPI
# worker threads. Only applies to SQLite.
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def init_db():
    """Create tables if they don't exist. Imports models so they register."""
    from . import models  # noqa: F401  (registers tables on Base)
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency: yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
