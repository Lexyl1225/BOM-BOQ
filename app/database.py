import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from app.config import settings

logger = logging.getLogger("bom_app")

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    """Dependency that yields a database session and closes it when done."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Columns added after the first release. create_all() only creates missing tables,
# so existing databases get these via ALTER TABLE.
_ADDED_COLUMNS = {
    "users": [
        ("must_change_password", "BOOLEAN NOT NULL DEFAULT 0"),
        ("password_changed_at", "DATETIME"),
    ],
}

def _migrate_columns():
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            existing = {c["name"] for c in inspector.get_columns(table)}
            for name, ddl in columns:
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
                    logger.info(f"Added column {table}.{name}")

def init_db():
    """Initialize database tables and run automatic seed service if required."""
    from app import models  # ensure models are registered
    Base.metadata.create_all(bind=engine)
    _migrate_columns()
    logger.info("Database schema initialized.")
    
    if settings.AUTO_SEED:
        from app.services.seed_service import seed_database
        with SessionLocal() as db:
            try:
                seed_database(db)
            except Exception as e:
                logger.error(f"Error during database auto-seeding: {e}", exc_info=True)

    from app.services.seed_service import normalize_department_names
    with SessionLocal() as db:
        try:
            normalize_department_names(db)
        except Exception as e:
            db.rollback()
            logger.error(f"Error normalizing department names: {e}", exc_info=True)

    # Register departments and issue API keys for any department that has none yet
    from app.services.api_key_service import sync_departments
    with SessionLocal() as db:
        try:
            added = sync_departments(db)
            if added:
                logger.info(f"Issued API keys for {added} new department(s).")
        except Exception as e:
            db.rollback()
            logger.error(f"Error syncing departments / API keys: {e}", exc_info=True)
