import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.config import settings
from backend.app.database import init_db, SessionLocal
from backend.app.services.embedding_service import embedding_service
from backend.app.models.document import Document
from backend.app.models.chunk import DocumentChunk

from backend.app.api.auth import router as auth_router
from backend.app.api.chats import router as chats_router
from backend.app.api.projects import router as projects_router
from backend.app.api.messages import router as messages_router
from backend.app.api.rag import router as rag_router
from backend.app.api.admin import router as admin_router
from backend.app.api.rag_inspect import router as rag_inspect_router
from backend.app.api.memories import router as memories_router
from backend.app.api.visuals import router as visuals_router
from backend.app.api.admin_files import router as admin_files_router


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize PostgreSQL and prepare the embedding model."""
    logger.info("Initializing PostgreSQL database and verifying tables...")

    # Fail startup if database initialization fails.
    init_db()

    # Recover any ingestion jobs interrupted by previous server shutdown or crash
    db = SessionLocal()
    try:
        from backend.app.ingestion.ingest import recover_interrupted_ingestions
        recovered = recover_interrupted_ingestions(db)
        if recovered > 0:
            logger.info("Recovered %s interrupted document ingestion(s) on startup.", recovered)
    except Exception as exc:
        logger.warning("Crash recovery check failed: %s", exc)
    finally:
        db.close()

    if settings.EMBEDDING_WARMUP_ON_STARTUP:
        logger.info("Warming the embedding model before accepting requests...")
        try:
            embedding_service.warm_up()
            logger.info("Embedding model warm-up completed.")
        except Exception:
            logger.exception("Embedding model warm-up failed.")
            raise

    logger.info("SAP Knowledge Assistant backend ready.")

    yield

    logger.info("Shutting down SAP Knowledge Assistant backend.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    description=(
        "Enterprise SAP Knowledge Assistant with Developer-Managed "
        "RAG and Strict Domain Boundaries"
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# CORS configuration.
# Restrict allow_origins to your frontend URL before production deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global error handler: avoid exposing internal stack traces to clients.
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        "Unhandled exception on %s: %s",
        request.url.path,
        exc,
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": (
                "An internal server error occurred. "
                "Please contact the administrator."
            )
        },
    )


# Register API routers.
app.include_router(auth_router, prefix=settings.API_V1_STR)
app.include_router(chats_router, prefix=settings.API_V1_STR)
app.include_router(projects_router, prefix=settings.API_V1_STR)
app.include_router(messages_router, prefix=settings.API_V1_STR)
app.include_router(rag_router, prefix=settings.API_V1_STR)
app.include_router(admin_router, prefix=settings.API_V1_STR)
app.include_router(rag_inspect_router, prefix=settings.API_V1_STR)
app.include_router(memories_router, prefix=settings.API_V1_STR)
app.include_router(visuals_router, prefix=settings.API_V1_STR)
app.include_router(admin_files_router, prefix=settings.API_V1_STR)


@app.get("/", tags=["Info"])
def root():
    return {
        "service": settings.PROJECT_NAME,
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "health": "/health",
        "api": "/api",
        "database": "PostgreSQL",
    }


@app.get("/health", tags=["Health"])
def health_check():
    """Report database connectivity and knowledge-base counts."""
    db = SessionLocal()

    try:
        doc_count = db.query(Document).count()
        chunk_count = db.query(DocumentChunk).count()

        return {
            "status": "healthy",
            "service": settings.PROJECT_NAME,
            "version": "1.0.0",
            "database": "PostgreSQL",
            "knowledge_base": {
                "documents_count": doc_count,
                "chunks_count": chunk_count,
                "model": settings.EMBEDDING_MODEL,
            },
        }
    except Exception:
        logger.exception("Health check failed.")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "database": "PostgreSQL",
            },
        )
    finally:
        db.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
