"""FastAPI application for the local TrustVault prototype."""

from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response

from .config import Settings, settings_from_env
from .database import connect, initialize_database, record_event
from .schemas import (
    AdminUserResponse, AuditResponse, AuthInput, DocumentResponse, ShareInput, ShareResponse,
    UserResponse, UserStatusInput,
)
from .security import create_session_token, hash_password, read_session_token, verify_password

ALLOWED_MIME = {
    ".csv": "text/csv", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".jpeg": "image/jpeg", ".jpg": "image/jpeg", ".md": "text/markdown", ".pdf": "application/pdf",
    ".png": "image/png", ".txt": "text/plain",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def share_status(*, expires_at: str | None, revoked_at: str | None, now: str) -> str:
    if revoked_at is not None:
        return "revoked"
    if expires_at is not None and expires_at <= now:
        return "expired"
    return "active"


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or settings_from_env()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        config.storage_dir.mkdir(parents=True, exist_ok=True)
        initialize_database(config.database_path)
        yield

    app = FastAPI(title="TrustVault API", version="0.1.0", lifespan=lifespan)
    app.state.settings = config
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.cors_origins), allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"], allow_headers=["Content-Type"],
    )

    async def current_user(request: Request) -> dict:
        token = request.cookies.get(config.cookie_name)
        user_id = read_session_token(token or "", config.secret_key)
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
        with connect(config.database_path) as db:
            row = db.execute(
                "SELECT id, email, display_name, role, is_active FROM users WHERE id = ?", (user_id,),
            ).fetchone()
        if row is None or not row["is_active"]:
            raise HTTPException(status_code=401, detail="Authentication required")
        return dict(row)

    async def require_admin(user: dict = Depends(current_user)) -> dict:
        if user["role"] != "admin":
            raise HTTPException(status_code=403, detail="Administrator access required")
        return user

    @app.get("/health")
    async def health() -> dict[str, str]:
        try:
            with connect(config.database_path) as db:
                db.execute("SELECT 1").fetchone()
            return {"status": "ok", "database": "ok"}
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Database unavailable") from exc

    @app.post("/api/auth/register", response_model=UserResponse, status_code=201)
    async def register(payload: AuthInput, response: Response) -> dict:
        user_id, now = str(uuid.uuid4()), utc_now()
        display_name = (payload.display_name or payload.email.split("@", 1)[0]).strip()
        try:
            with connect(config.database_path) as db:
                db.execute(
                    "INSERT INTO users(id, email, display_name, password_hash, created_at, role, is_active) "
                    "VALUES (?, ?, ?, ?, ?, 'user', 1)",
                    (user_id, payload.email, display_name, hash_password(payload.password), now),
                )
                record_event(db, event_type="account_registered", actor_id=user_id, details="{}", created_at=now)
        except Exception as exc:
            if "UNIQUE constraint failed" in str(exc):
                raise HTTPException(status_code=409, detail="An account with this email already exists") from exc
            raise
        response.set_cookie(
            config.cookie_name, create_session_token(user_id, config.secret_key, config.session_hours),
            httponly=True, secure=config.cookie_secure, samesite="lax", max_age=config.session_hours * 3600,
            path="/",
        )
        return {"id": user_id, "email": payload.email, "display_name": display_name, "role": "user"}

    @app.post("/api/auth/login", response_model=UserResponse)
    async def login(payload: AuthInput, response: Response) -> dict:
        with connect(config.database_path) as db:
            row = db.execute("SELECT * FROM users WHERE email = ? COLLATE NOCASE", (payload.email,)).fetchone()
            if row is None or not verify_password(row["password_hash"], payload.password):
                raise HTTPException(status_code=401, detail="Invalid email or password")
            if not row["is_active"]:
                raise HTTPException(status_code=403, detail="This account has been disabled")
            now = utc_now()
            record_event(db, event_type="account_login", actor_id=row["id"], created_at=now)
        response.set_cookie(
            config.cookie_name, create_session_token(row["id"], config.secret_key, config.session_hours),
            httponly=True, secure=config.cookie_secure, samesite="lax", max_age=config.session_hours * 3600,
            path="/",
        )
        return {"id": row["id"], "email": row["email"], "display_name": row["display_name"],
                "role": row["role"]}

    @app.post("/api/auth/logout", status_code=204)
    async def logout() -> Response:
        response = Response(status_code=204)
        response.delete_cookie(config.cookie_name, httponly=True, secure=config.cookie_secure, samesite="lax", path="/")
        return response

    @app.get("/api/auth/me", response_model=UserResponse)
    async def me(user: dict = Depends(current_user)) -> dict:
        return user

    @app.get("/api/admin/users", response_model=list[AdminUserResponse])
    async def list_users(_: dict = Depends(require_admin)) -> list[dict]:
        with connect(config.database_path) as db:
            rows = db.execute(
                "SELECT u.id, u.email, u.display_name, u.role, u.is_active, u.created_at, "
                "COUNT(d.id) AS document_count FROM users AS u LEFT JOIN documents AS d ON d.owner_id = u.id "
                "GROUP BY u.id ORDER BY u.created_at DESC",
            ).fetchall()
        return [{**dict(row), "is_active": bool(row["is_active"])} for row in rows]

    @app.patch("/api/admin/users/{user_id}", response_model=AdminUserResponse)
    async def set_user_status(
        user_id: str, payload: UserStatusInput, admin: dict = Depends(require_admin),
    ) -> dict:
        with connect(config.database_path) as db:
            target = db.execute(
                "SELECT id, email, display_name, role, is_active, created_at FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            if target is None:
                raise HTTPException(status_code=404, detail="User not found")
            if target["id"] == admin["id"]:
                raise HTTPException(status_code=400, detail="You cannot disable your own account")
            if target["role"] == "admin":
                raise HTTPException(status_code=400, detail="Administrator accounts cannot be managed here")
            db.execute("UPDATE users SET is_active = ? WHERE id = ?", (int(payload.is_active), user_id))
            event_type = "account_activated" if payload.is_active else "account_deactivated"
            record_event(
                db, event_type=event_type, actor_id=admin["id"],
                details=json.dumps({"managed_user_email": target["email"]}), created_at=utc_now(),
            )
            doc_count = db.execute(
                "SELECT COUNT(*) FROM documents WHERE owner_id = ?", (user_id,),
            ).fetchone()[0]
        return {**dict(target), "is_active": payload.is_active, "document_count": doc_count}

    @app.post("/api/documents", response_model=DocumentResponse, status_code=201)
    async def upload_document(file: UploadFile = File(...), user: dict = Depends(current_user)) -> dict:
        original_name = Path(file.filename or "").name.strip()
        suffix = Path(original_name).suffix.lower()
        if not original_name or suffix not in ALLOWED_MIME:
            raise HTTPException(status_code=415, detail="Unsupported file type")
        document_id, storage_name, now = str(uuid.uuid4()), f"{uuid.uuid4().hex}{suffix}", utc_now()
        target = config.storage_dir / storage_name
        size = 0
        try:
            with target.open("xb") as out:
                while chunk := await file.read(64 * 1024):
                    size += len(chunk)
                    if size > config.max_upload_bytes:
                        raise HTTPException(status_code=413, detail="File exceeds the upload size limit")
                    out.write(chunk)
            if size == 0:
                raise HTTPException(status_code=400, detail="Empty files are not allowed")
            with connect(config.database_path) as db:
                db.execute(
                    "INSERT INTO documents(id, owner_id, original_name, storage_name, content_type, size_bytes, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (document_id, user["id"], original_name, storage_name, ALLOWED_MIME[suffix], size, now),
                )
                record_event(db, event_type="document_uploaded", actor_id=user["id"], document_id=document_id,
                             details=json.dumps({"name": original_name, "size_bytes": size}), created_at=now)
        except Exception:
            target.unlink(missing_ok=True)
            raise
        finally:
            await file.close()
        return {"id": document_id, "original_name": original_name, "content_type": ALLOWED_MIME[suffix],
                "size_bytes": size, "created_at": now}

    @app.get("/api/documents", response_model=list[DocumentResponse])
    async def list_documents(user: dict = Depends(current_user)) -> list[dict]:
        with connect(config.database_path) as db:
            rows = db.execute(
                "SELECT d.id, d.original_name, d.content_type, d.size_bytes, d.created_at, "
                "CASE WHEN d.owner_id = ? THEN 1 ELSE 0 END AS is_owner, "
                "(SELECT owner.display_name FROM users AS owner WHERE owner.id = d.owner_id) AS shared_by, "
                "CASE WHEN d.owner_id = ? THEN 1 ELSE EXISTS (SELECT 1 FROM document_shares AS s "
                "WHERE s.document_id = d.id AND s.user_id = ? AND s.can_view = 1 AND s.revoked_at IS NULL "
                "AND (s.expires_at IS NULL OR s.expires_at > ?)) END AS can_view, "
                "CASE WHEN d.owner_id = ? THEN 1 ELSE EXISTS (SELECT 1 FROM document_shares AS s "
                "WHERE s.document_id = d.id AND s.user_id = ? AND s.can_download = 1 AND s.revoked_at IS NULL "
                "AND (s.expires_at IS NULL OR s.expires_at > ?)) END AS can_download, "
                "(SELECT s.expires_at FROM document_shares AS s WHERE s.document_id = d.id AND s.user_id = ? "
                "AND s.revoked_at IS NULL ORDER BY s.created_at DESC LIMIT 1) AS expires_at "
                "FROM documents AS d WHERE d.owner_id = ? OR EXISTS (SELECT 1 FROM document_shares AS s "
                "WHERE s.document_id = d.id AND s.user_id = ? AND s.revoked_at IS NULL "
                "AND (s.expires_at IS NULL OR s.expires_at > ?)) "
                "ORDER BY d.created_at DESC",
                (user["id"], user["id"], user["id"], now := utc_now(), user["id"], user["id"], now,
                 user["id"], user["id"], user["id"], now),
            ).fetchall()
        return [dict(row) for row in rows]

    @app.post("/api/documents/{document_id}/shares", response_model=ShareResponse, status_code=201)
    async def create_share(
        document_id: str, payload: ShareInput, user: dict = Depends(current_user),
    ) -> dict:
        now = utc_now()
        expires_at = payload.expires_at.astimezone(timezone.utc).isoformat(timespec="microseconds") if payload.expires_at else None
        if expires_at is not None and expires_at <= now:
            raise HTTPException(status_code=422, detail="Expiry must be in the future")
        with connect(config.database_path) as db:
            document = db.execute(
                "SELECT id FROM documents WHERE id = ? AND owner_id = ?", (document_id, user["id"]),
            ).fetchone()
            if document is None:
                raise HTTPException(status_code=404, detail="Document not found")
            recipient = db.execute(
                "SELECT id, email, display_name FROM users WHERE email = ? COLLATE NOCASE", (payload.email,),
            ).fetchone()
            if recipient is None:
                raise HTTPException(status_code=404, detail="No TrustVault account uses that email yet")
            if recipient["id"] == user["id"]:
                raise HTTPException(status_code=400, detail="You already have access to this document")
            existing = db.execute(
                "SELECT id, revoked_at, expires_at FROM document_shares WHERE document_id = ? AND user_id = ?",
                (document_id, recipient["id"]),
            ).fetchone()
            if existing:
                share_id = existing["id"]
                db.execute(
                    "UPDATE document_shares SET granted_by = ?, created_at = ?, can_view = ?, can_download = ?, "
                    "expires_at = ?, revoked_at = NULL WHERE id = ?",
                    (user["id"], now, int(payload.can_view), int(payload.can_download), expires_at, share_id),
                )
                event_type = "document_share_updated"
            else:
                share_id = str(uuid.uuid4())
                db.execute(
                    "INSERT INTO document_shares(id, document_id, user_id, granted_by, created_at, can_view, "
                    "can_download, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (share_id, document_id, recipient["id"], user["id"], now, int(payload.can_view),
                     int(payload.can_download), expires_at),
                )
                event_type = "document_shared"
            record_event(
                db, event_type=event_type, actor_id=user["id"], document_id=document_id,
                details=json.dumps({"recipient_email": recipient["email"], "can_view": payload.can_view,
                                    "can_download": payload.can_download, "expires_at": expires_at}),
                created_at=now,
            )
        return {"id": share_id, "email": recipient["email"], "display_name": recipient["display_name"],
                "created_at": now, "can_view": payload.can_view, "can_download": payload.can_download,
                "expires_at": expires_at, "revoked_at": None, "status": "active"}

    @app.get("/api/documents/{document_id}/shares", response_model=list[ShareResponse])
    async def list_shares(document_id: str, user: dict = Depends(current_user)) -> list[dict]:
        with connect(config.database_path) as db:
            owned = db.execute(
                "SELECT 1 FROM documents WHERE id = ? AND owner_id = ?", (document_id, user["id"]),
            ).fetchone()
            if owned is None:
                raise HTTPException(status_code=404, detail="Document not found")
            rows = db.execute(
                "SELECT s.id, u.email, u.display_name, s.created_at, s.can_view, s.can_download, "
                "s.expires_at, s.revoked_at FROM document_shares AS s "
                "JOIN users AS u ON u.id = s.user_id WHERE s.document_id = ? ORDER BY s.created_at",
                (document_id,),
            ).fetchall()
        now = utc_now()
        return [{**dict(row), "can_view": bool(row["can_view"]), "can_download": bool(row["can_download"]),
                 "status": share_status(expires_at=row["expires_at"], revoked_at=row["revoked_at"], now=now)}
                for row in rows]

    @app.delete("/api/documents/{document_id}/shares/{share_id}", status_code=204)
    async def revoke_share(document_id: str, share_id: str, user: dict = Depends(current_user)) -> Response:
        with connect(config.database_path) as db:
            owned = db.execute(
                "SELECT 1 FROM documents WHERE id = ? AND owner_id = ?", (document_id, user["id"]),
            ).fetchone()
            if owned is None:
                raise HTTPException(status_code=404, detail="Document not found")
            share = db.execute(
                "SELECT u.email, s.revoked_at FROM document_shares AS s JOIN users AS u ON u.id = s.user_id "
                "WHERE s.id = ? AND s.document_id = ?", (share_id, document_id),
            ).fetchone()
            if share is None:
                raise HTTPException(status_code=404, detail="Share not found")
            if share["revoked_at"] is not None:
                raise HTTPException(status_code=404, detail="Share is already revoked")
            revoked_at = utc_now()
            db.execute("UPDATE document_shares SET revoked_at = ? WHERE id = ?", (revoked_at, share_id))
            record_event(
                db, event_type="document_access_revoked", actor_id=user["id"], document_id=document_id,
                details=json.dumps({"recipient_email": share["email"]}), created_at=revoked_at,
            )
        return Response(status_code=204)

    def get_accessible_document(document_id: str, user_id: str, permission: str) -> dict:
        if permission not in {"can_view", "can_download"}:
            raise ValueError("Invalid document permission")
        with connect(config.database_path) as db:
            row = db.execute(
                "SELECT d.id, d.original_name, d.storage_name, d.content_type FROM documents AS d "
                "WHERE d.id = ? AND (d.owner_id = ? OR EXISTS (SELECT 1 FROM document_shares AS s "
                f"WHERE s.document_id = d.id AND s.user_id = ? AND s.{permission} = 1 "
                "AND s.revoked_at IS NULL AND (s.expires_at IS NULL OR s.expires_at > ?)))",
                (document_id, user_id, user_id, utc_now()),
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Document not found")
        return dict(row)

    @app.get("/api/documents/{document_id}/view")
    async def view_document(document_id: str, user: dict = Depends(current_user)) -> Response:
        row = get_accessible_document(document_id, user["id"], "can_view")
        target = config.storage_dir / row["storage_name"]
        if not target.is_file():
            raise HTTPException(status_code=404, detail="Document file not found")
        with connect(config.database_path) as db:
            record_event(db, event_type="document_viewed", actor_id=user["id"], document_id=document_id,
                         created_at=utc_now())
        return Response(
            content=target.read_bytes(), media_type=row["content_type"],
            headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(row['original_name'])}"},
        )

    @app.get("/api/documents/{document_id}/download")
    async def download_document(document_id: str, user: dict = Depends(current_user)) -> Response:
        row = get_accessible_document(document_id, user["id"], "can_download")
        target = config.storage_dir / row["storage_name"]
        if not target.is_file():
            raise HTTPException(status_code=404, detail="Document file not found")
        with connect(config.database_path) as db:
            record_event(db, event_type="document_downloaded", actor_id=user["id"], document_id=document_id,
                         created_at=utc_now())
        return Response(
            content=target.read_bytes(),
            media_type=row["content_type"],
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(row['original_name'])}"},
        )

    @app.get("/api/audit", response_model=list[AuditResponse])
    async def audit_events(user: dict = Depends(current_user)) -> list[dict]:
        with connect(config.database_path) as db:
            rows = db.execute(
                "SELECT id, event_type, document_id, details, created_at FROM audit_events "
                "WHERE actor_id = ? ORDER BY id DESC LIMIT 100", (user["id"],),
            ).fetchall()
        return [dict(row) for row in rows]

    return app


app = create_app()
