from app.db.database import Base, engine

from app.db import models


def init_db():
    """Create all registered database tables.

    Returns:
        None.
    """

    print("Creating database tables...")

    tables = list(Base.metadata.tables.keys())

    print("Registered tables:")
    for table in tables:
        print(f"  - {table}")

    Base.metadata.create_all(bind=engine)

    print("Database initialized successfully.")


if __name__ == "__main__":
    init_db()
