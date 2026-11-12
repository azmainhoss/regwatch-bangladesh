from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database.session import get_async_db
from backend.app.modules.identity.deps import get_current_user
from backend.app.modules.identity.models import User
from backend.app.modules.research.service import ResearchQueryResponse, ResearchService

router = APIRouter(prefix="/research", tags=["Regulatory Research Assistant"])


class ResearchQueryRequest(BaseModel):
    query: str
    document_id: Optional[UUID] = None
    institution_id: Optional[UUID] = None


@router.post("/query", response_model=ResearchQueryResponse)
async def query_regulatory_assistant(
    payload: ResearchQueryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Submits a regulatory research question. Returns source-grounded answers with exact citations.
    """
    if not payload.query or len(payload.query.strip()) < 3:
        raise HTTPException(status_code=400, detail="Query string too short.")

    return await ResearchService.query_regulatory_knowledge(
        db=db,
        query=payload.query,
        document_id=payload.document_id,
        institution_id=payload.institution_id,
        user=current_user,
    )
