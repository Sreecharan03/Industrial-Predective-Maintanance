"""Grounded LLM query endpoint (ADR-018)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from senseminds.api.deps import AppState, current_user, state

router = APIRouter(prefix="/llm", tags=["llm"], dependencies=[Depends(current_user)])


class QueryRequest(BaseModel):
    unit: str
    question: str = ""
    persona: str = "reliability_engineer"


@router.post("/query")
def query(req: QueryRequest, app: AppState = Depends(state)) -> dict:
    answer = app.llm.answer(req.unit, req.question, req.persona)
    return answer.model_dump(mode="json")
