from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..db import db
from ..services.ask import ask as run_ask

router = APIRouter(tags=["ask"])


class AskBody(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    lang: str = "ar"


@router.post("/ask")
def ask(body: AskBody):
    with db() as conn:
        return run_ask(conn, body.question, lang=body.lang)
