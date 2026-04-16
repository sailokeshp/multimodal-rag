import logging

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.answer_service import AnswerService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/answer", tags=["answer"])


class AnswerRequest(BaseModel):
    query: str
    context: list[str]


class AnswerResponse(BaseModel):
    answer: str


@router.post("", response_model=AnswerResponse)
async def generate_answer(body: AnswerRequest) -> AnswerResponse:
    """
    Generate a grounded answer from explicitly provided context snippets.
    Useful for re-generating an answer without re-running retrieval.
    """
    svc = AnswerService()
    answer = await svc.generate_from_context(query=body.query, context=body.context)
    return AnswerResponse(answer=answer)
