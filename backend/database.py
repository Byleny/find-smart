import os
from urllib.parse import quote

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()


def build_database_url(url: str, encryption_key: str) -> str:
    """Con una clave, la misma base SQLite se abre con SQLCipher (cifrado AES-256 en reposo):
    sin la clave, el archivo es ilegible. Sin clave se usa SQLite normal."""
    if not encryption_key:
        return url
    if not url.startswith("sqlite:///"):
        raise ValueError("DB_ENCRYPTION_KEY solo aplica a bases de datos SQLite")
    path = url[len("sqlite:///"):]
    return f"sqlite+pysqlcipher://:{quote(encryption_key, safe='')}@/{path}"


DATABASE_URL = build_database_url(
    os.getenv("DATABASE_URL", "sqlite:///./finsmart.db"),
    os.getenv("DB_ENCRYPTION_KEY", ""),
)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
