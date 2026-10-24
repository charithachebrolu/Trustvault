"""Environment-backed settings for the local TrustVault prototype."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    secret_key: str
    database_path: Path
    storage_dir: Path
    max_upload_bytes: int = 10 * 1024 * 1024
    cookie_secure: bool = False
    cookie_name: str = "trustvault_session"
    session_hours: int = 8
    cors_origins: tuple[str, ...] = ("http://localhost:5173",)


def settings_from_env() -> Settings:
    load_dotenv()
    secret = os.getenv("TRUSTVAULT_SECRET_KEY", "").strip()
    if len(secret) < 32:
        raise RuntimeError(
            "TRUSTVAULT_SECRET_KEY must be set to at least 32 characters. "
            "Copy .env.example to .env and generate a secret before starting the API."
        )
    project_dir = Path(__file__).resolve().parents[2]
    backend_dir = project_dir / "backend"

    def resolve_path(value: str, default: Path) -> Path:
        path = Path(value) if value else default
        return path if path.is_absolute() else project_dir / path

    database_path = resolve_path(os.getenv("TRUSTVAULT_DATABASE_PATH", ""), backend_dir / "trustvault.db")
    storage_dir = resolve_path(os.getenv("TRUSTVAULT_STORAGE_DIR", ""), backend_dir / "uploads")
    max_upload_bytes = int(os.getenv("TRUSTVAULT_MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
    if max_upload_bytes < 1:
        raise RuntimeError("TRUSTVAULT_MAX_UPLOAD_BYTES must be positive")
    origins = tuple(
        origin.strip()
        for origin in os.getenv("TRUSTVAULT_CORS_ORIGINS", "http://localhost:5173").split(",")
        if origin.strip()
    )
    return Settings(
        secret_key=secret,
        database_path=database_path,
        storage_dir=storage_dir,
        max_upload_bytes=max_upload_bytes,
        cookie_secure=os.getenv("TRUSTVAULT_COOKIE_SECURE", "false").lower() in {"1", "true", "yes"},
        session_hours=int(os.getenv("TRUSTVAULT_SESSION_HOURS", "8")),
        cors_origins=origins,
    )
