import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def build_database_url() -> str:
    """Build the database connection URL from environment variables.

    Returns:
        A SQLAlchemy-compatible database connection URL.
    """

    host = os.getenv("MARIADB_HOST", "localhost")
    port = os.getenv("MARIADB_PORT", "3306")
    database = os.getenv("MARIADB_DATABASE", "")
    user = os.getenv("MARIADB_USER", "")
    password = os.getenv("MARIADB_PASSWORD", "")

    return (
        f"mysql+pymysql://{user}:{password}"
        f"@{host}:{port}/{database}"
    )


engine = create_engine(
    build_database_url(),
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


def get_db():
    """Provide a database session and close it after use.

    Returns:
        A generator that yields a SQLAlchemy database session.
    """

    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()
