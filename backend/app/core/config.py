"""Application Configuration Module

Single Organization Edition: Physio One
Reads environment variables with fallback defaults.
"""
from typing import List, Optional
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Application
    APP_NAME: str = "Physio One WhatsApp AI Agent"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    APP_SECRET: str = "default-insecure-secret-key-change-in-production-64char"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    BACKEND_CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    @field_validator("BACKEND_CORS_ORIGINS")
    @classmethod
    def validate_cors_origins(cls, v: List[str], info) -> List[str]:
        env = info.data.get("ENVIRONMENT", "development")
        if env in ("staging", "production"):
            for origin in v:
                if origin == "*" or origin.strip() == "*":
                    raise ValueError(f"Wildcard CORS origin '*' is strictly prohibited in {env} environment.")
        return v

    # Database
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "physio_admin"
    POSTGRES_PASSWORD: str = "physio_secure_password"
    POSTGRES_DB: str = "physio_one_db"
    POSTGRES_SOCKET_DIR: Optional[str] = None  # e.g., /cloudsql/project:region:instance
    POSTGRES_POOL_SIZE: int = 5
    POSTGRES_MAX_OVERFLOW: int = 5
    POSTGRES_POOL_RECYCLE: int = 1800
    POSTGRES_POOL_TIMEOUT: int = 30
    DATABASE_URL: Optional[str] = None
    DATABASE_URL_SYNC: Optional[str] = None

    @property
    def async_database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        socket_dir = self.POSTGRES_SOCKET_DIR or (self.POSTGRES_SERVER if self.POSTGRES_SERVER and self.POSTGRES_SERVER.startswith("/") else None)
        if socket_dir:
            return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@/{self.POSTGRES_DB}?host={socket_dir}"
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def sync_database_url(self) -> str:
        if self.DATABASE_URL_SYNC:
            return self.DATABASE_URL_SYNC
        socket_dir = self.POSTGRES_SOCKET_DIR or (self.POSTGRES_SERVER if self.POSTGRES_SERVER and self.POSTGRES_SERVER.startswith("/") else None)
        if socket_dir:
            return f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@/{self.POSTGRES_DB}?host={socket_dir}"
        return f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # Redis & Celery — DEPRECATED (Task 14): no application code uses Redis/Celery.
    # Durable state is PostgreSQL-backed; scheduling is Cloud Tasks/Scheduler.
    # Retained only for backward-compatible env parsing; do not add new usage.
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # Security & Tokens
    JWT_SECRET_KEY: str = "default-jwt-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    COOKIE_SECURE: bool = False

    # Clinic Rules (Physio One)
    CLINIC_NAME: str = "Physio One"
    CLINIC_TIMEZONE: str = "Asia/Kolkata"
    CLINIC_OPEN_TIME: str = "09:00"
    CLINIC_CLOSE_TIME: str = "20:00"
    CLINIC_CLOSED_WEEKDAYS: List[int] = [0]  # Sunday = 0
    DEFAULT_APPOINTMENT_DURATION_MINUTES: int = 45

    # Storage
    STORAGE_BACKEND: str = "local"
    LOCAL_STORAGE_PATH: str = "./storage"

    # Scheduled Automation & Follow-ups (Task 11)
    AUTOMATION_OUTBOUND_ENABLED: bool = False
    AUTOMATION_WORKER_INTERVAL_SECONDS: int = 60
    AUTOMATION_WORKER_SECRET_TOKEN: str = "default-automation-worker-secret-token"

    # Cloud Run & Cloud Tasks Worker Security (Task 13)
    CLOUD_RUN_SERVICE_URL: Optional[str] = None
    WORKER_SERVICE_ACCOUNT_EMAIL: Optional[str] = None
    OIDC_AUDIENCE: Optional[str] = None
    REQUIRE_OIDC_IN_PRODUCTION: bool = False

    # Cloud Tasks dispatch (Task 14) — disabled by default; PostgreSQL job rows
    # remain the source of truth, Cloud Tasks is only a delivery mechanism.
    CLOUD_TASKS_ENABLED: bool = False
    GCP_PROJECT_ID: Optional[str] = None
    CLOUD_TASKS_LOCATION: str = "asia-south1"
    CLOUD_TASKS_INBOUND_QUEUE: str = "physio-inbound"
    CLOUD_TASKS_AUTOMATION_QUEUE: str = "physio-automation"
    CLOUD_TASKS_CAMPAIGN_QUEUE: str = "physio-campaigns"
    WORKER_BASE_URL: Optional[str] = None  # public Cloud Run API URL tasks POST to

    # Staging Isolation & Outbound Safeguards (Task 17)
    STAGING_ALLOWLIST_PHONE_NUMBERS: List[str] = []
    STAGING_MOCK_OUTBOUND: bool = False
    APPOINTMENTS_READ_ONLY: bool = False
    CAMPAIGNS_DRAFT_ONLY: bool = False
    DEFAULT_AI_INBOUND_MODE: str = "disabled"


def calculate_connection_budget(
    api_instances: int = 3,
    api_pool_size: int = 5,
    api_max_overflow: int = 5,
    worker_job_instances: int = 1,
    worker_pool_size: int = 2,
    worker_max_overflow: int = 1,
    migration_connections: int = 1,
    admin_connections: int = 5,
    db_tier: str = "db-custom-1-3840",
) -> dict:
    """Calculate maximum potential concurrent PostgreSQL connections across all system components.

    Verifies that total concurrent connections stay safely within the Cloud SQL tier's max_connections ceiling.
    """
    tier_limits = {
        "db-f1-micro": 25,
        "db-g1-small": 50,
        "db-custom-1-3840": 100,
        "db-custom-2-7680": 200,
    }
    max_tier_conns = tier_limits.get(db_tier, 100)
    api_max = api_instances * (api_pool_size + api_max_overflow)
    worker_max = worker_job_instances * (worker_pool_size + worker_max_overflow)
    total = api_max + worker_max + migration_connections + admin_connections
    headroom = max_tier_conns - total
    is_safe = headroom >= 0
    return {
        "db_tier": db_tier,
        "tier_max_connections": max_tier_conns,
        "api_max_connections": api_max,
        "worker_max_connections": worker_max,
        "migration_connections": migration_connections,
        "admin_connections": admin_connections,
        "total_peak_connections": total,
        "headroom": headroom,
        "is_safe": is_safe,
    }


settings = Settings()

