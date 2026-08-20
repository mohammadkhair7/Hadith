# AdvancedHadith

Unified Hadith knowledge platform merging three corpora — **hadith.db**
(sunna.alifta.gov.sa), **alifta.db** (www.alifta.net archive) and **alshamela.db**
(Al-Maktaba Al-Shamela) — into one PostgreSQL + Apache AGE knowledge base with:

- Tashkeel-insensitive keyword search (Postgres FTS + pg_trgm)
- Semantic search (`gemini-embedding-001` vectors in Redis 8, HNSW)
- NL2SQL + NL2CYPHER natural-language question answering (`gemini-3-flash-preview`, auto-fallback to `gemini-2.5-flash`)
- Narrator knowledge graph (رجال الحديث) on Apache AGE with a bounded-subgraph explorer
- Manual, incremental, idempotent pipelines for embeddings, translations and indexing
- Kalimat.dev-first hadith English translations with Gemini fallback
- `Arabic-lib`: unified Arabic NLP layer (Farasa / CAMeL Tools / AlKhalil2)

Full architecture: [`docs/ADVANCED_HADITH_REQUIREMENTS_ARCHITECTURE.md`](docs/ADVANCED_HADITH_REQUIREMENTS_ARCHITECTURE.md)
· Decision log: [`docs/DECISIONS.md`](docs/DECISIONS.md)

## Repository layout

```
backend/     FastAPI application (REST API /api/v1)
frontend/    React 19 + Vite + Tailwind SPA (RTL-first, ar/en i18n)
etl/         Local ETL: SQLite sources -> unified Postgres schema
Arabic-lib/  arabiclib Python package (NLP engines, indexing, neural models)
ops/         Deployment / infra scripts (Railway, local docker bootstrap)
docs/        Architecture, decisions, reports
```

## Local development

Prereqs: Python 3.10+, Node 22+, Docker (running `apache/age` PG16 on
`127.0.0.1:5456` and `redis:8` on `localhost:6379`).

```powershell
# 1. env: copy .env.example -> .env.local and fill values (never committed)

# 2. database schema
python etl/migrate.py            # applies etl/schema.sql to LOCAL_PG_URL

# 3. load the three source databases (resumable)
python etl/load_all.py

# 4. backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080

# 5. frontend
cd frontend
npm install
npm run dev                      # http://localhost:5173
```

## Data policy

The SQLite sources and the Postgres contents are **never committed** (see
`.gitignore`). Railway Postgres is populated by running the ETL against
`DATABASE_PUBLIC_URL`. All costly pipelines (embeddings, translations,
indexing, model training) are manual and idempotent.
