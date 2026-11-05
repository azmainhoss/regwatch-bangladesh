from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class SourceBase(BaseModel):
    institution_id: UUID
    name: str
    source_type: str = "WEB_CRAWLER"
    base_url: Optional[str] = None
    config: Dict[str, Any] = {}
    is_active: bool = True


class SourceCreate(SourceBase):
    pass


class SourceRead(SourceBase):
    id: UUID
    last_checked_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SourceRunRead(BaseModel):
    id: UUID
    source_id: UUID
    run_type: str
    status: str
    discovered_count: int
    downloaded_count: int
    error_count: int
    started_at: datetime
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
