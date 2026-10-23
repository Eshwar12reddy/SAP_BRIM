from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict
from backend.app.schemas.citation import CitationResponse, WebSourceResponse

class MessageCreate(BaseModel):
    content: str = Field(default="", max_length=10000)
    attachment_ids: Optional[List[str]] = Field(default=None, description="Optional list of uploaded attachment IDs")

class MessageResponse(BaseModel):
    id: str
    chat_id: str
    role: str
    content: str
    source_type: Optional[str] = None
    selected_source: Optional[str] = None
    kb_relevance_score: Optional[float] = Field(default=None, ge=0, le=100)
    kb_threshold: Optional[float] = Field(default=75, ge=0, le=100)
    fallback_reason: Optional[str] = None
    stage_timings_ms: Dict[str, float] = {}
    web_search_used: Optional[bool] = False
    grounding_score: Optional[float] = Field(
        default=None, ge=0, le=1,
        description="Evidence-support estimate: supported claims / all claims, with partial support worth 0.5."
    )
    kb_grounding_score: Optional[float] = Field(default=None, ge=0, le=1)
    web_grounding_score: Optional[float] = Field(default=None, ge=0, le=1)
    grounding_status: Optional[str] = None
    grounding_method: Optional[str] = None
    grounding_summary: Optional[str] = None
    grounding_claims: List[Dict[str, Any]] = []
    is_in_rag_pipeline: Optional[bool] = None
    kb_score: Optional[float] = None
    web_score: Optional[float] = None
    winning_score: Optional[float] = None
    verification_status: Optional[str] = None
    internal_evidence_confidence: Optional[float] = None
    selected_evidence_quality: Optional[float] = None
    external_search_used: Optional[bool] = False
    created_at: datetime
    citations: List[CitationResponse] = []
    web_sources: List[WebSourceResponse] = []
    follow_up_questions: List[str] = []
    used_memories: Optional[List[Dict[str, Any]]] = None
    used_memory_ids: Optional[List[str]] = None
    previous_context_used: Optional[bool] = False
    visuals: Optional[List[Dict[str, Any]]] = None
    attachments: Optional[List[Dict[str, Any]]] = None
    feedback: Optional[str] = None
    feedback_comment: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class MessageFeedbackRequest(BaseModel):
    rating: str = Field(..., pattern="^(up|down)$", description="User rating: 'up' or 'down'")
    comment: Optional[str] = Field(None, max_length=1000, description="Optional text feedback")


class MessageFeedbackResponse(BaseModel):
    message_id: str
    feedback: str
    feedback_comment: Optional[str] = None
    status: str = "success"
