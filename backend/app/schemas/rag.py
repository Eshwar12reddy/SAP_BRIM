from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from backend.app.schemas.citation import CitationResponse, WebSourceResponse

class RAGQueryRequest(BaseModel):
    chat_id: Optional[str] = None
    query: str

class RAGQueryResponse(BaseModel):
    answer: str
    source_type: str  # 'knowledge_base', 'web', 'refusal', 'error', 'combined'
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
    selected_source: Optional[str] = None
    kb_relevance_score: Optional[float] = Field(default=None, ge=0, le=100)
    kb_threshold: Optional[float] = Field(default=75, ge=0, le=100)
    fallback_reason: Optional[str] = None
    stage_timings_ms: Dict[str, float] = {}
    web_search_used: Optional[bool] = False
    verification_status: Optional[str] = None
    internal_evidence_confidence: Optional[float] = None
    selected_evidence_quality: Optional[float] = None
    external_search_used: Optional[bool] = False
    citations: List[CitationResponse] = []
    web_sources: List[WebSourceResponse] = []
    follow_up_questions: List[str] = []
    selection_summary: Optional[str] = None
    chat_id: Optional[str] = None
    message_id: Optional[str] = None
