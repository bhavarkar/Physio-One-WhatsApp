"""Pydantic Schemas for Users and Roles

Single Organization Edition: Physio One Clinic.
"""
import re
import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, field_validator

EMAIL_REGEX = re.compile(r"^[\w\.\+\-]+@[\w\-]+\.[a-zA-Z]{2,}$")


class RoleSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class PermissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    resource: str
    action: str


class RoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: Optional[str] = None
    permissions: List[PermissionResponse] = []


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    last_login_at: Optional[datetime] = None
    created_at: datetime
    role: RoleSummary


class UserCreateRequest(BaseModel):
    email: str
    password: str
    full_name: str
    role_id: uuid.UUID

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        clean_email = v.strip().lower()
        if not EMAIL_REGEX.match(clean_email):
            raise ValueError("Invalid email address format.")
        return clean_email

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        return v

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        clean_name = v.strip()
        if len(clean_name) < 2:
            raise ValueError("Full name must be at least 2 characters long.")
        return clean_name


class UserUpdateRequest(BaseModel):
    email: Optional[str] = None
    full_name: Optional[str] = None
    role_id: Optional[uuid.UUID] = None
    is_active: Optional[bool] = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            clean_email = v.strip().lower()
            if not EMAIL_REGEX.match(clean_email):
                raise ValueError("Invalid email address format.")
            return clean_email
        return v

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            clean_name = v.strip()
            if len(clean_name) < 2:
                raise ValueError("Full name must be at least 2 characters long.")
            return clean_name
        return v


class UserListResponse(BaseModel):
    users: List[UserResponse]
    total: int
    page: int
    page_size: int

