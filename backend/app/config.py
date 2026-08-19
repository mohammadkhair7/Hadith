"""Settings: local dev reads AdvancedHadith/.env.local + Hadith.chat/.env;
on Railway everything comes from service variables."""
import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

_ROOT = Path(__file__).resolve().parents[2]          # AdvancedHadith/
load_dotenv(_ROOT / ".env.local")
load_dotenv(_ROOT.parent / ".env")                   # shared keys (never committed)


class Settings(BaseSettings):
    # database: DATABASE_URL wins (Railway); LOCAL_PG_URL is the dev fallback
    database_url: str = os.getenv("DATABASE_URL") or os.getenv("LOCAL_PG_URL") or ""
    redis_url: str = os.getenv("REDIS_URL") or os.getenv("LOCAL_REDIS_URL") or "redis://localhost:6379/0"

    jwt_secret: str = os.getenv("JWT_SECRET_KEY", "dev-secret-change-me")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    access_token_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    refresh_token_days: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))

    gemini_api_key: str = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
    llm_model: str = os.getenv("LLM_MODEL", "gemini-2.5-flash")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")
    embedding_dimensions: int = int(os.getenv("EMBEDDING_DIMENSIONS", "768"))

    kalimat_api_key: str = os.getenv("KALIMAT_API_KEY", "")

    default_language: str = os.getenv("DEFAULT_LANGUAGE", "ar")
    supported_languages: str = os.getenv("SUPPORTED_LANGUAGES", "ar,en")

    cors_origins: str = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")

    # Redis namespace prefix (the local instance is shared with other projects)
    redis_prefix: str = os.getenv("REDIS_PREFIX", "ah")


settings = Settings()
