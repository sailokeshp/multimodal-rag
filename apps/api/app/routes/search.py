import logging
import time

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.search import SearchRequest, SearchResponse
from app.services.retrieval_service import RetrievalService
from app.services.answer_service import AnswerService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/search", tags=["search"])


@router.post("", response_model=SearchResponse)
async def search(
    body: SearchRequest,
    db: AsyncSession = Depends(get_db),
) -> SearchResponse:
    t0 = time.monotonic()

    retrieval = RetrievalService(db)
    results, query_type = await retrieval.search(
        query=body.query,
        top_k_text=body.topK,
        top_k_image=body.topK,
        top_k_final=body.topK,
        filters=body.filters,
    )

    answer = None
    if body.includeAnswer and results:
        answer_svc = AnswerService()
        answer = await answer_svc.generate(query=body.query, results=results)

    latency_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "Search complete: query_type=%s results=%d latency_ms=%d",
        query_type,
        len(results),
        latency_ms,
    )

    return SearchResponse(queryType=query_type, answer=answer, results=results)
