import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from api.guest_session import GuestSessionStore
from api.rag_service import retrieval_service
from api.routes import (
    _delete_analysis_rag_scope,
    analysis_store,
    delete_owner_rag_scopes,
    document_store,
    rag_answer_cache,
    rag_answer_daily_budget,
    rag_answer_observability,
    rag_answer_rate_limiter,
    rag_transaction_lock,
    router,
    upload_rate_limiter,
    upload_store,
)
from config import (
    CORS_ORIGIN_REGEX,
    CORS_ORIGINS,
    GUEST_COOKIE_SECURE,
    GUEST_SESSION_COOKIE,
    GUEST_SESSION_TTL_MINUTES,
)
from src.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)
guest_session_store = GuestSessionStore(timedelta(minutes=GUEST_SESSION_TTL_MINUTES))


async def cleanup_expired_temporary_data() -> None:
    while True:
        await asyncio.sleep(60)
        removed_uploads = upload_store.cleanup_expired()
        expired_analyses = analysis_store.pop_expired()
        removed_analyses = len(expired_analyses)
        removed_documents = 0
        for analysis in expired_analyses:
            removed_documents += _delete_analysis_rag_scope(
                analysis.owner_scope_id, analysis.analysis_id
            )
        with rag_transaction_lock:
            expired_documents = document_store.pop_expired()
            removed_documents += len(expired_documents)
            expired_analysis_scopes = set()
            for document in expired_documents:
                scope = (
                    document.metadata.owner_scope_id,
                    document.metadata.analysis_id,
                )
                expired_analysis_scopes.add(scope)
                try:
                    retrieval_service.delete_document(
                        document.metadata.owner_scope_id,
                        document.metadata.analysis_id,
                        document.metadata.document_id,
                    )
                except Exception:
                    logger.exception("Could not remove expired document from the evidence index")
            for owner_scope_id, analysis_id in expired_analysis_scopes:
                if not document_store.active_documents(owner_scope_id, analysis_id):
                    retrieval_service.drop_scope(owner_scope_id, analysis_id)
        expired_guest_sessions = guest_session_store.pop_expired()
        removed_guest_sessions = len(expired_guest_sessions)
        for session in expired_guest_sessions:
            removed_documents += delete_owner_rag_scopes(session.session_id)
            rag_answer_rate_limiter.drop_owner(session.session_id)
            upload_rate_limiter.drop_owner(session.session_id)
        rag_answer_rate_limiter.cleanup_expired()
        upload_rate_limiter.cleanup_expired()
        if removed_uploads or removed_analyses or removed_documents or removed_guest_sessions:
            logger.info(
                "Removed %d uploads, %d analyses, %d documents, and %d guest sessions",
                removed_uploads,
                removed_analyses,
                removed_documents,
                removed_guest_sessions,
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Serve the generic sales workflow without downloading demo data at startup."""
    cleanup_task = asyncio.create_task(cleanup_expired_temporary_data())
    try:
        yield
    finally:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
        upload_store.clear()
        analysis_store.clear()
        document_store.clear()
        retrieval_service.clear()
        rag_answer_observability.clear()
        rag_answer_rate_limiter.clear()
        rag_answer_cache.clear()
        rag_answer_daily_budget.clear()
        upload_rate_limiter.clear()
        guest_session_store.clear()


app = FastAPI(title="Ecommerce Sales Intelligence API", lifespan=lifespan)


@app.middleware("http")
async def attach_guest_session(request: Request, call_next):
    """Issue a frictionless anonymous identity and keep it inaccessible to JavaScript."""
    session, created = guest_session_store.resolve(request.cookies.get(GUEST_SESSION_COOKIE))
    request.state.guest_session_id = session.session_id
    response = await call_next(request)
    if created:
        response.set_cookie(
            key=GUEST_SESSION_COOKIE,
            value=session.session_id,
            max_age=GUEST_SESSION_TTL_MINUTES * 60,
            httponly=True,
            secure=GUEST_COOKIE_SECURE,
            samesite="lax",
            path="/",
        )
    return response


app.add_middleware(
    CORSMiddleware,
    # Explicit origins win when configured (production); otherwise fall back to
    # the localhost regex so any Vite dev port works.
    allow_origins=CORS_ORIGINS,
    allow_origin_regex=None if CORS_ORIGINS else CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

app.include_router(router)
