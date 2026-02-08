import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.models import Base

load_dotenv()

def get_db_url() -> str:
    user = os.getenv("POSTGRES_USER", "hive_user")
    password = os.getenv("POSTGRES_PASSWORD", "hive1234")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "hive_dynamics")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"

def get_db_session():
    engine = create_engine(get_db_url())
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()

def init_db():
    engine = create_engine(get_db_url())
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created")

if __name__ == "__main__":
    init_db()
