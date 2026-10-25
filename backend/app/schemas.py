"""API response models."""

import re
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AuthInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=256)
    display_name: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Enter a valid email address")
        return value


class AdminBootstrapInput(AuthInput):
    bootstrap_token: str = Field(min_length=32, max_length=512)


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: str
    role: str = "user"


class UserStatusInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_active: bool


class AdminUserResponse(BaseModel):
    id: str
    email: str
    display_name: str
    role: str
    is_active: bool
    created_at: str
    document_count: int


class DocumentResponse(BaseModel):
    id: str
    original_name: str
    content_type: str
    size_bytes: int
    created_at: str
    is_owner: bool = True
    shared_by: str | None = None
    can_view: bool = True
    can_download: bool = True
    expires_at: str | None = None


class ShareInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)
    can_view: bool = True
    can_download: bool = True
    expires_at: datetime | None = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Enter a valid email address")
        return value

    @field_validator("expires_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None:
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("Expiry must include a timezone")
            return value.astimezone(timezone.utc)
        return None

    @model_validator(mode="after")
    def require_permission(self) -> "ShareInput":
        if not self.can_view and not self.can_download:
            raise ValueError("Grant at least view or download access")
        return self


class ShareResponse(BaseModel):
    id: str
    email: str
    display_name: str
    created_at: str
    can_view: bool
    can_download: bool
    expires_at: str | None
    revoked_at: str | None
    status: Literal["active", "expired", "revoked"]


class AuditResponse(BaseModel):
    id: int
    event_type: str
    document_id: str | None
    details: str
    created_at: str
