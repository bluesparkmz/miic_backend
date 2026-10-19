import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Load environment variables from .env file if available
load_dotenv()

# Read DATABASE_URL from environment (e.g. postgresql://user:password@host:port/dbname)
raw_url = os.getenv("DATABASE_URL")

if raw_url:
    # Normalize postgres:// to postgresql:// for SQLAlchemy 1.4+ / 2.0+ compatibility
    if raw_url.startswith("postgres://"):
        raw_url = raw_url.replace("postgres://", "postgresql://", 1)
    
    SQLALCHEMY_DATABASE_URL = raw_url
    # PostgreSQL engine with auto-reconnection and pooling
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )
else:
    # Default fallback to SQLite if DATABASE_URL is not set
    DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "miic.db")
    SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False}  # Needed for SQLite in multi-threaded FastAPI
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
