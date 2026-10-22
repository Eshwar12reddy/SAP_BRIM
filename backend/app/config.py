
import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parent.parent.parent
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # Application
    PROJECT_NAME: str = "SAP Knowledge Assistant"
    API_V1_STR: str = "/api"
    DEBUG: bool = False

    # PostgreSQL only — SQLite fallback is disabled.
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5434/sap_assistant",
    )

    # JWT security
    JWT_SECRET: str = os.getenv(
        "JWT_SECRET",
        "sap-super-secret-jwt-key-2026-production-ready",
    )
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # Admin key for developer ingestion
    ADMIN_API_KEY: str = os.getenv(
        "ADMIN_API_KEY",
        "sap-admin-dev-secret-key-999",
    )

    # LLM settings
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openrouter")
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_MODEL: str = os.getenv(
        "LLM_MODEL",
        "nvidia/nemotron-3-super-120b-a12b:free",
    )
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")

    # Embedding and RAG parameters
    EMBEDDING_MODEL: str = os.getenv(
        "EMBEDDING_MODEL",
        "all-MiniLM-L6-v2",
    )
    EMBEDDING_DIM: int = 384

    TOP_K: int = int(os.getenv("TOP_K", "8"))
    RERANK_TOP_K: int = int(os.getenv("RERANK_TOP_K", "8"))
    MAX_LLM_CONTEXT_CHARS: int = int(
        os.getenv("MAX_LLM_CONTEXT_CHARS", "12000")
    )
    LLM_MAX_OUTPUT_TOKENS: int = int(
        os.getenv("LLM_MAX_OUTPUT_TOKENS", "2048")
    )
    LLM_REQUEST_TIMEOUT_SECONDS: float = float(
        os.getenv("LLM_REQUEST_TIMEOUT_SECONDS", "10")
    )
    QUERY_REWRITE_TIMEOUT_SECONDS: float = float(
        os.getenv("QUERY_REWRITE_TIMEOUT_SECONDS", "2")
    )

    EMBEDDING_WARMUP_ON_STARTUP: bool = (
        os.getenv("EMBEDDING_WARMUP_ON_STARTUP", "true").lower()
        in ("true", "1")
    )

    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "1200"))
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "200"))
    MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50"))

    SIMILARITY_THRESHOLD: float = float(
        os.getenv("SIMILARITY_THRESHOLD", "0.60")
    )
    GROUNDING_THRESHOLD: float = float(
        os.getenv("GROUNDING_THRESHOLD", "0.65")
    )

    # Evidence score threshold for Knowledge Base vs Tavily fallback (0.0 to 1.0)
    KB_CONFIDENCE_THRESHOLD: float = max(0.0, min(1.0, float(
        os.getenv("KB_CONFIDENCE_THRESHOLD", "0.75")
    )))
    INTERNAL_EVIDENCE_THRESHOLD: float = max(0.0, min(1.0, float(
        os.getenv("INTERNAL_EVIDENCE_THRESHOLD", os.getenv("KB_CONFIDENCE_THRESHOLD", "0.75"))
    )))
    ANSWER_GROUNDING_THRESHOLD: float = float(
        os.getenv("ANSWER_GROUNDING_THRESHOLD", "0.90")
    )
    CONFIDENCE_ACCEPTANCE_THRESHOLD: float = float(
        os.getenv("CONFIDENCE_ACCEPTANCE_THRESHOLD", "0.75")
    )
    MAX_GROUNDING_REPAIR_ATTEMPTS: int = int(
        os.getenv("MAX_GROUNDING_REPAIR_ATTEMPTS", "1")
    )
    FOLLOWUP_QUESTION_COUNT: int = int(
        os.getenv("FOLLOWUP_QUESTION_COUNT", "3")
    )

    # Tavily web search latency controls
    TAVILY_MAX_RESULTS: int = int(
        os.getenv("TAVILY_MAX_RESULTS", "5")
    )
    TAVILY_TIMEOUT_SECONDS: float = float(
        os.getenv("TAVILY_TIMEOUT_SECONDS", "8.0")
    )
    TAVILY_CONNECT_TIMEOUT_SECONDS: float = float(
        os.getenv("TAVILY_CONNECT_TIMEOUT_SECONDS", "3.0")
    )
    TAVILY_READ_TIMEOUT_SECONDS: float = float(
        os.getenv("TAVILY_READ_TIMEOUT_SECONDS", "8.0")
    )
    TAVILY_OVERALL_DEADLINE_SECONDS: float = float(
        os.getenv("TAVILY_OVERALL_DEADLINE_SECONDS", "15.0")
    )
    TAVILY_MAX_RETRIES: int = int(
        os.getenv("TAVILY_MAX_RETRIES", "1")
    )
    TAVILY_MAX_QUERIES: int = int(
        os.getenv("TAVILY_MAX_QUERIES", "2")
    )

    # Web fallback and general-question policy
    WEB_FALLBACK_ENABLED: bool = (
        os.getenv("WEB_FALLBACK_ENABLED", "true").lower()
        in ("true", "1")
    )
    WEB_SEARCH_API_KEY: str = os.getenv("WEB_SEARCH_API_KEY", "")
    GENERAL_QUESTIONS_ENABLED: bool = (
        os.getenv("GENERAL_QUESTIONS_ENABLED", "true").lower()
        in ("true", "1")
    )

    # Question-driven visuals and diagrams
    ENABLE_VISUAL_GENERATION: bool = (
        os.getenv("ENABLE_VISUAL_GENERATION", "true").lower()
        in ("true", "1")
    )
    ENABLE_GENERATIVE_IMAGES: bool = (
        os.getenv("ENABLE_GENERATIVE_IMAGES", "false").lower()
        in ("true", "1")
    )
    MAX_VISUALS_PER_ANSWER: int = int(
        os.getenv("MAX_VISUALS_PER_ANSWER", "2")
    )
    VISUAL_GENERATION_TIMEOUT_SECONDS: float = float(
        os.getenv("VISUAL_GENERATION_TIMEOUT_SECONDS", "30.0")
    )
    VISUAL_DAILY_QUOTA_PER_USER: int = int(
        os.getenv("VISUAL_DAILY_QUOTA_PER_USER", "50")
    )
    VISUAL_STORAGE_DIR: Path = BASE_DIR / "media" / "visuals"

    RESTRICT_VISUALS_TO_TECHNICAL: bool = (
        os.getenv("RESTRICT_VISUALS_TO_TECHNICAL", "true").lower()
        in ("true", "1")
    )
    IMAGE_GENERATION_PROVIDER: str = os.getenv(
        "IMAGE_GENERATION_PROVIDER",
        "openai",
    )
    IMAGE_GENERATION_MODEL: str = os.getenv(
        "IMAGE_GENERATION_MODEL",
        "dall-e-3",
    )
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # Vision & Screenshot Troubleshooting settings
    VISION_PROVIDER: str = os.getenv("VISION_PROVIDER", "openai")
    VISION_MODEL: str = os.getenv("VISION_MODEL", "gpt-4o-mini")
    MAX_IMAGE_MB: int = int(os.getenv("MAX_IMAGE_MB", "5"))
    MAX_IMAGES_PER_MESSAGE: int = int(os.getenv("MAX_IMAGES_PER_MESSAGE", "3"))

    # Canonical knowledge-base paths
    KNOWLEDGE_BASE_DIR: Path = (
        ROOT_DIR / "knowledge_base"
        if (ROOT_DIR / "knowledge_base").exists()
        else BASE_DIR / "knowledge_base"
    )

    DOCUMENTS_DIR: Path = (
        ROOT_DIR / "knowledge_base" / "documents"
        if (ROOT_DIR / "knowledge_base" / "documents").exists()
        else BASE_DIR / "knowledge_base" / "documents"
    )

    FULL_RAG_DATA_DIR: Path = (
        ROOT_DIR / "knowledge_base" / "the full rag data sap"
        if (ROOT_DIR / "knowledge_base" / "the full rag data sap").exists()
        else BASE_DIR / "knowledge_base" / "the full rag data sap"
    )

    # Environment file discovery
    model_config = SettingsConfigDict(
        env_file=(
            str(BASE_DIR / ".env")
            if (BASE_DIR / ".env").exists()
            else (
                str(BASE_DIR / "app" / ".env")
                if (BASE_DIR / "app" / ".env").exists()
                else str(ROOT_DIR / ".env")
            )
        ),
        extra="allow",
    )


settings = Settings()
