"""FastAPI Main Application Entry Point

Single Organization Edition: Physio One Clinic.
"""
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.v1 import auth, users, whatsapp, webhooks

app = FastAPI(
    title=settings.APP_NAME,
    description="Production-ready WhatsApp AI Agent Platform for Physio One Clinic.",
    version="1.0.0-draft",
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
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

app.include_router(api_v1_router)

