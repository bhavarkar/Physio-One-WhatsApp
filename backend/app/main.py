"""FastAPI Main Application Entry Point

Single Organization Edition: Physio One Clinic.
"""
from fastapi import FastAPI, APIRouter, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.v1 import auth, users, whatsapp, webhooks, appointments
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

app = FastAPI(
    title=settings.APP_NAME,
    description="Production-ready WhatsApp AI Agent Platform for Physio One Clinic.",
    version="1.0.0-draft",
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
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

app.include_router(api_v1_router)

