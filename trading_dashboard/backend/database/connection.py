from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from config import DATABASE_URL
import os

os.makedirs(os.path.dirname(DATABASE_URL.replace("sqlite:///", "")),
            exist_ok=True)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    from database.models import (PriceCache, InferenceCache,
                                  BacktestResult, SystemParams,
                                  Metadata)
    Base.metadata.create_all(bind=engine)
