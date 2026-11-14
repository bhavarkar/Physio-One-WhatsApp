"""FastAPI Main Application Entry Point

Single Organization Edition: Physio One Clinic.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import async_engine, Base
import app.models  # noqa: F401
from app.api.v1 import (
    auth,
    users,
    whatsapp,
    webhooks,
    appointments,
    llm,
    agents,
    tools,
    knowledge,
    conversations,
    ai_inbound,
    appointment_workflows,
)
from app.services.agent_service import AgentService
from app.services.workflow_service import AppointmentWorkflowService
from app.core.database import AsyncSessionLocal
from app.services.appointment_service import (
    AppointmentServiceError,
    SundayRestrictionError,
    OperatingHoursViolationError,
    PastAppointmentError,
    AppointmentConflictError,
    InvalidStatusTransitionError,
    AppointmentNotFoundError,
    PatientNotFoundError,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # If running with SQLite (e.g. local quickstart or testing), ensure tables are created
    if async_engine.dialect.name == "sqlite":
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    if settings.ENVIRONMENT != "testing":
        try:
            async with AsyncSessionLocal() as session:
                await AgentService.ensure_default_ai_entities(session)
                await AppointmentWorkflowService.get_or_create_settings(session)
        except Exception as e:
            # Non-blocking log if DB is pending migration
            import logging
            logging.getLogger("physio_one").warning(f"Default AI initialization deferred: {e}")
    yield
    await async_engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    description="Production-ready WhatsApp AI Agent Platform for Physio One Clinic.",
    version="1.0.0-draft",
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
    lifespan=lifespan,
)

@app.exception_handler(AppointmentServiceError)
async def appointment_service_error_handler(request: Request, exc: AppointmentServiceError):
    status_code = 400
    if isinstance(exc, (SundayRestrictionError, OperatingHoursViolationError, PastAppointmentError)):
        status_code = getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422)
    elif isinstance(exc, (AppointmentConflictError, InvalidStatusTransitionError)):
        status_code = 409
    elif isinstance(exc, (AppointmentNotFoundError, PatientNotFoundError)):
        status_code = 404
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
            "detail": exc.message,
        },
    )

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Root health check endpoint
@app.get("/health")
@app.get("/api/v1/health")
async def health_check():
    """Service health check endpoint."""
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "environment": settings.ENVIRONMENT,
        "version": "1.0.0-draft",
    }


# Mount v1 API routers
api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(auth.router)
api_v1_router.include_router(users.router)
api_v1_router.include_router(whatsapp.router)
api_v1_router.include_router(webhooks.router)
api_v1_router.include_router(appointments.router)
api_v1_router.include_router(llm.router)
api_v1_router.include_router(agents.router)
api_v1_router.include_router(tools.router)
api_v1_router.include_router(knowledge.router)
api_v1_router.include_router(conversations.router)
api_v1_router.include_router(ai_inbound.router)
api_v1_router.include_router(appointment_workflows.router)

app.include_router(api_v1_router)

