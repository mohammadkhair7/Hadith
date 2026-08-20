from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import close_pool, open_pool
from .routers import (admin, analytics, ask, auth, narrators, passages, search,
                      subjects, user_items, works)


@asynccontextmanager
async def lifespan(app: FastAPI):
    open_pool()
    yield
    close_pool()


app = FastAPI(
    title="AdvancedHadith API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/v1/docs",
    openapi_url="/api/v1/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API = "/api/v1"
app.include_router(auth.router, prefix=API)
app.include_router(works.router, prefix=API)
app.include_router(passages.router, prefix=API)
app.include_router(search.router, prefix=API)
app.include_router(subjects.router, prefix=API)
app.include_router(user_items.router, prefix=API)
app.include_router(admin.router, prefix=API)
app.include_router(ask.router, prefix=API)
app.include_router(narrators.router, prefix=API)
app.include_router(analytics.router, prefix=API)


@app.get(f"{API}/health")
def health():
    return {"status": "ok", "languages": settings.supported_languages.split(",")}
