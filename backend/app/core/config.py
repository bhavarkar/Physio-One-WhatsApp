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

    # Database
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "physio_admin"
    POSTGRES_PASSWORD: str = "physio_secure_password"
    POSTGRES_DB: str = "physio_one_db"
    DATABASE_URL: Optional[str] = None
    DATABASE_URL_SYNC: Optional[str] = None

    @property
    def async_database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def sync_database_url(self) -> str:
        if self.DATABASE_URL_SYNC:
            return self.DATABASE_URL_SYNC
        return f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # Redis & Celery
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


settings = Settings()

