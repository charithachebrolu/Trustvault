"""API response models."""

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


class ShareInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Enter a valid email address")
        return value


class ShareResponse(BaseModel):
    id: str
    email: str
    display_name: str
    created_at: str


class AuditResponse(BaseModel):
    id: int
    event_type: str
    document_id: str | None
    details: str
    created_at: str
