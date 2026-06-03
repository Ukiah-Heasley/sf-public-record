from __future__ import annotations

from fastapi import APIRouter

from ..search.hybrid import hybrid_search, lexical_search
from .deps import SettingsDep
from .schemas import SearchRequest, SearchResponse, SearchResultItem

router = APIRouter(tags=["search"])


@router.post("/search", response_model=SearchResponse)
def search(request: SearchRequest, settings: SettingsDep) -> SearchResponse:
    if request.lexical_only:
        response = lexical_search(
            db_path=settings.db_path,
            query=request.query,
            date_start=request.date_start,
            date_end=request.date_end,
            document_types=request.document_types,
            limit=request.limit,
        )
    else:
        response = hybrid_search(
            db_path=settings.db_path,
            settings=settings,
            query=request.query,
            date_start=request.date_start,
            date_end=request.date_end,
            document_types=request.document_types,
            limit=request.limit,
        )

    return SearchResponse(
        query=response.query,
        answer_stub=response.answer_stub,
        results=[
            SearchResultItem(
                chunk_id=result.chunk_id,
                document_id=result.document_id,
                title=result.title,
                source_type=result.source_type,
                hearing_date=result.hearing_date,
                page_start=result.page_start,
                page_end=result.page_end,
                citation_label=result.citation_label,
                text=result.text,
                score=result.score,
                url=result.url,
            )
            for result in response.results
        ],
    )
