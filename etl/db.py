"""Postgres connection helper for the ETL. Reads AdvancedHadith/.env.local
(gitignored) or process env. Set ETL_TARGET=railway to load into Railway
(DATABASE_PUBLIC_URL) instead of the local docker AGE instance."""
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env.local")
load_dotenv(ROOT.parent / ".env")  # shared Hadith.chat env (API keys etc.)


def pg_url() -> str:
    if os.getenv("ETL_TARGET", "local") == "railway":
        url = os.getenv("DATABASE_PUBLIC_URL")
        if not url:
            raise SystemExit("ETL_TARGET=railway but DATABASE_PUBLIC_URL is not set")
        return url
    url = os.getenv("LOCAL_PG_URL")
    if not url:
        raise SystemExit("LOCAL_PG_URL not set (see AdvancedHadith/.env.local)")
    return url


def connect(autocommit: bool = False) -> psycopg.Connection:
    return psycopg.connect(pg_url(), autocommit=autocommit)


SOURCES = {
    "hadith": ROOT.parent / "data" / "hadith.db",
    "alifta": ROOT.parent / "Alifta.chat" / "data" / "alifta.db",
    "alshamela": ROOT.parent / "Al-Shamela" / "alshamela.db",
}
