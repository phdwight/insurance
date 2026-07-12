import os

from sqlalchemy import Engine, create_engine

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        url = os.environ.get(
            "DATABASE_URL",
            "postgresql+psycopg://insurance:insurance@localhost:5432/insurance",
        )
        _engine = create_engine(url, pool_pre_ping=True)
    return _engine
