from typing import Any, Literal

from pydantic import BaseModel, Field


class SearchFilters(BaseModel):
    fileTypes: list[str] = Field(default_factory=list)


class SearchRequest(BaseModel):
    query: str
    topK: int = 10
    filters: SearchFilters = Field(default_factory=SearchFilters)
    includeAnswer: bool = False


class DocumentChunkResult(BaseModel):
    resultType: Literal["document_chunk"] = "document_chunk"
    fileId: str
    fileName: str
    pageStart: int | None = None
    pageEnd: int | None = None
    snippet: str
    score: float


class ImageResult(BaseModel):
    resultType: Literal["image"] = "image"
    fileId: str
    fileName: str
    imageId: str
    thumbnailUrl: str | None = None
    caption: str | None = None
    score: float


class SearchResponse(BaseModel):
    queryType: str
    answer: str | None = None
    results: list[Any]  # DocumentChunkResult | ImageResult
