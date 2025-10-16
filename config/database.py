from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from config.settings import settings

class Base(DeclarativeBase):
    pass

engine = create_engine(f"sqlite:///{settings.DB_PATH}", echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, autocommit=False)

def init_db():
    from core import models  # noqa: F401
    Base.metadata.create_all(bind=engine)