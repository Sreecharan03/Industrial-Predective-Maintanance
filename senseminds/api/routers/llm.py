"""Grounded LLM query endpoint (ADR-018)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from senseminds.api.deps import AppState, current_user, state

router = APIRouter(prefix="/llm", tags=["llm"], dependencies=[Depends(current_user)])


class Turn(BaseModel):
    role: str          # "user" | "assistant"
    content: str


class QueryRequest(BaseModel):
    unit: str
    question: str = ""
    persona: str = "reliability_engineer"
    history: list[Turn] = []


@router.post("/query")
def query(req: QueryRequest, app: AppState = Depends(state)) -> dict:
    # Memory shapes only how the answer is phrased. Evidence is re-retrieved fresh
    # every turn — history can never change what is true (ADR-018 §7).
    history = [(t.role, t.content) for t in req.history]
    answer = app.llm.answer(req.unit, req.question, req.persona, history)
    out = answer.model_dump(mode="json")
    out["model"] = app.llm.model_name          # so the UI can flag offline mode
    return out
