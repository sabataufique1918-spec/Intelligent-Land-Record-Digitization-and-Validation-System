from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATABASE_URL

# SQLite is accepted only as a quick local fallback; PostgreSQL is the target database.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def add_missing_columns() -> list[str]:
    """Add columns that exist in the models but not yet in the database.

    create_all() only creates missing tables, so this keeps an existing database
    usable when new (nullable) columns are added. It never drops or changes columns.
    """
    added = []
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing:
                    continue
                column_type = column.type.compile(dialect=engine.dialect)
                conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {column.name} {column_type}'))
                added.append(f"{table.name}.{column.name}")
            for index in table.indexes:
                index.create(bind=conn, checkfirst=True)
    return added


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
