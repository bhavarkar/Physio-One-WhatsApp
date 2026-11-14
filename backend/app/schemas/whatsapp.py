"""Pydantic Schemas for WhatsApp Integration and Messaging

Single Organization Edition: Physio One.
Guarantees secret token masking and strong input validation.
"""
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, ConfigDict, field_validator


class WhatsAppAccountCreateRequest(BaseModel):
    provider: str = Field(..., description="Provider type: 'meta' (Meta Cloud API) or 'ycloud'")
    account_name: str = Field(..., min_length=2, max_length=100, description="Internal display label")
    phone_number_id: str = Field(..., min_length=1, max_length=100, description="Meta Phone Number ID or YCloud account identifier")
    display_phone_number: str = Field(..., min_length=5, max_length=30, description="International format e.g. +919876543210")
    business_account_id: Optional[str] = Field(None, max_length=100, description="Meta Business Account ID (WABA)")
    webhook_verify_token: str = Field(..., min_length=8, max_length=255, description="Secret token for webhook registration")
    access_token: str = Field(..., min_length=5, description="Meta System User Access Token or YCloud API Key")
    secret_key: Optional[str] = Field(None, description="Meta App Secret or YCloud Webhook Secret")
    provider_config: Optional[Dict[str, Any]] = None
    is_active: bool = True

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        prov = v.lower().strip()
        if prov not in ("meta", "meta_cloud", "ycloud"):
            raise ValueError("Provider must be either 'meta' or 'ycloud'.")
        return "meta" if prov in ("meta", "meta_cloud") else "ycloud"


class WhatsAppAccountUpdateRequest(BaseModel):
    account_name: Optional[str] = Field(None, min_length=2, max_length=100)
    display_phone_number: Optional[str] = Field(None, min_length=5, max_length=30)
    business_account_id: Optional[str] = None
    webhook_verify_token: Optional[str] = Field(None, min_length=8, max_length=255)
    access_token: Optional[str] = Field(None, min_length=5, description="Provide only if updating the stored secret")
    secret_key: Optional[str] = Field(None, description="Provide only if updating the stored secret")
    provider_config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class WhatsAppAccountResponse(BaseModel):
    id: uuid.UUID
    provider: str
    account_name: str
    phone_number_id: str
    business_account_id: Optional[str] = None
    display_phone_number: str
    webhook_verify_token: str
    has_access_token: bool = True
    has_secret_key: bool = False
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConnectionTestResponse(BaseModel):
    is_valid: bool
    display_name: Optional[str] = None
    phone_number: Optional[str] = None
    error: Optional[str] = None


class TestMessageRequest(BaseModel):
    recipient_phone: str = Field(..., min_length=7, max_length=25, description="Recipient phone number with country code")
    message_text: str = Field("Physio One WhatsApp integration test verification.", max_length=1000)


class MessageSendResponse(BaseModel):
    success: bool
    message_id: Optional[str] = None
    provider_message_id: Optional[str] = None
    status: str
    error: Optional[str] = None

