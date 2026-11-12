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

def init_db():
    """Initialize database tables and run automatic seed service if required."""
    from app import models  # ensure models are registered
    Base.metadata.create_all(bind=engine)
    logger.info("Database schema initialized.")
    
    if settings.AUTO_SEED:
        from app.services.seed_service import seed_database
        with SessionLocal() as db:
            try:
                seed_database(db)
            except Exception as e:
                logger.error(f"Error during database auto-seeding: {e}", exc_info=True)
