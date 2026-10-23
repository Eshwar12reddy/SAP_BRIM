import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, field_validator

class MemoryResponse(BaseModel):
    id: str
    user_id: str
    memory_type: str
    summary: str
    entities: Optional[Any] = None
    provenance: str
    status: str
    confidence: float
    superseded_by: Optional[str] = None
    source_chat_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    last_accessed_at: Optional[datetime] = None

    @field_validator("entities", mode="before")
    @classmethod
    def parse_entities(cls, v: Any) -> Any:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return v
        return v

    model_config = ConfigDict(from_attributes=True)


class MemoryUpdate(BaseModel):
    summary: Optional[str] = None
    memory_type: Optional[str] = None
    status: Optional[str] = None
    entities: Optional[Any] = None


class ScenarioMemoryResponse(BaseModel):
    id: str
    user_id: str
    scenario_title: str
    symptoms: Optional[str] = None
    affected_modules: Optional[Any] = None
    entities: Optional[Any] = None
    investigation_steps: Optional[Any] = None
    confirmed_findings: Optional[Any] = None
    attempted_solutions: Optional[Any] = None
    unresolved_questions: Optional[Any] = None
    hypotheses: Optional[Any] = None
    status: str
    source_chat_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    last_accessed_at: Optional[datetime] = None

    @field_validator(
        "affected_modules", "entities", "investigation_steps",
        "confirmed_findings", "attempted_solutions", "unresolved_questions",
        "hypotheses", mode="before"
    )
    @classmethod
    def parse_json_fields(cls, v: Any) -> Any:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return v
        return v

    model_config = ConfigDict(from_attributes=True)


class ScenarioUpdate(BaseModel):
    scenario_title: Optional[str] = None
    symptoms: Optional[str] = None
    affected_modules: Optional[List[str]] = None
    status: Optional[str] = None
    confirmed_findings: Optional[List[str]] = None
    attempted_solutions: Optional[List[str]] = None
    unresolved_questions: Optional[List[str]] = None


class MemorySettingsResponse(BaseModel):
    memory_enabled: bool


class MemorySettingsUpdate(BaseModel):
    memory_enabled: bool


class MemoryListResponse(BaseModel):
    items: List[MemoryResponse]
    total: int
    limit: int
    offset: int
