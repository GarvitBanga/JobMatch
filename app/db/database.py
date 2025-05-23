"""
Database connection and session management
"""

from sqlmodel import SQLModel, create_engine, Session
from typing import Generator

from ..core.config import settings

# Create database engine
engine = create_engine(
    settings.database_url,
    echo=settings.debug,  # Log SQL queries in debug mode
    pool_pre_ping=True,   # Verify connections before use
    pool_recycle=300,     # Recycle connections every 5 minutes
)

def create_db_and_tables():
    """Create database tables"""
    SQLModel.metadata.create_all(engine)

def get_session() -> Generator[Session, None, None]:
    """Get database session for dependency injection"""
    with Session(engine) as session:
        yield session

async def init_db():
    """Initialize database with default data if needed"""
    # TODO: Add any default data initialization
    pass 