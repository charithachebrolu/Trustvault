import os
from pathlib import Path

import httpx
import pytest

os.environ.setdefault("TRUSTVAULT_SECRET_KEY", "test-module-import-key-with-more-than-32-characters")

from app.config import Settings
from app.database import connect
from app.main import create_app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client(tmp_path: Path):
    settings = Settings(
        secret_key="test-only-secret-key-with-more-than-32-bytes",
        database_path=tmp_path / "test.sqlite3",
        storage_dir=tmp_path / "files",
        max_upload_bytes=1024 * 1024,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as test_client:
            yield test_client


async def register(client: httpx.AsyncClient, email: str) -> dict:
    response = await client.post("/api/auth/register", json={
        "email": email, "password": "correct horse battery staple", "display_name": email.split("@")[0],
    })
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.anyio
async def test_health_initializes_database(client: httpx.AsyncClient) -> None:
    assert (await client.get("/health")).json() == {"status": "ok", "database": "ok"}


@pytest.mark.anyio
async def test_registration_hashes_password_and_sets_http_only_cookie(client: httpx.AsyncClient, tmp_path: Path) -> None:
    await register(client, "user@example.com")
    cookie = client.cookies.get("trustvault_session")
    assert cookie
    with connect(tmp_path / "test.sqlite3") as db:
        stored = db.execute("SELECT password_hash FROM users").fetchone()[0]
    assert stored != "correct horse battery staple"
    assert stored.startswith("$argon2")
    assert (await client.get("/api/auth/me")).json()["email"] == "user@example.com"


@pytest.mark.anyio
async def test_invalid_credentials_and_short_password_are_rejected(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/auth/register", json={"email": "bad", "password": "short"})
    assert response.status_code == 422
    await register(client, "user@example.com")
    response = await client.post("/api/auth/login", json={"email": "user@example.com", "password": "wrong password value"})
    assert response.status_code == 401


@pytest.mark.anyio
async def test_upload_list_download_and_audit(client: httpx.AsyncClient) -> None:
    await register(client, "owner@example.com")
    response = await client.post("/api/documents", files={"file": ("notes.txt", b"private notes", "text/plain")})
    assert response.status_code == 201, response.text
    item = response.json()
    assert item["size_bytes"] == len(b"private notes")
    assert (await client.get("/api/documents")).json()[0]["id"] == item["id"]
    download = await client.get(f"/api/documents/{item['id']}/download")
    assert download.status_code == 200
    assert download.content == b"private notes"
    events = (await client.get("/api/audit")).json()
    assert {entry["event_type"] for entry in events} >= {"document_uploaded", "document_downloaded"}


@pytest.mark.anyio
async def test_documents_require_auth_and_are_isolated_by_owner(client: httpx.AsyncClient) -> None:
    await register(client, "owner@example.com")
    doc = (await client.post("/api/documents", files={"file": ("private.txt", b"secret", "text/plain")})).json()
    client.cookies.clear()
    assert (await client.get("/api/documents")).status_code == 401
    await register(client, "other@example.com")
    assert (await client.get("/api/documents")).json() == []
    assert (await client.get(f"/api/documents/{doc['id']}/download")).status_code == 404


@pytest.mark.anyio
async def test_upload_validates_extension_and_size(tmp_path: Path) -> None:
    settings = Settings("test-only-secret-key-with-more-than-32-bytes", tmp_path / "size.sqlite3", tmp_path / "files", max_upload_bytes=5)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            await register(client, "user@example.com")
            rejected_type = await client.post("/api/documents", files={"file": ("bad.exe", b"123", "application/octet-stream")})
            rejected_size = await client.post("/api/documents", files={"file": ("large.txt", b"123456", "text/plain")})
            assert rejected_type.status_code == 415
            assert rejected_size.status_code == 413
            assert (await client.get("/api/documents")).json() == []


@pytest.mark.anyio
async def test_logout_clears_session(client: httpx.AsyncClient) -> None:
    await register(client, "user@example.com")
    assert (await client.post("/api/auth/logout")).status_code == 204
    assert (await client.get("/api/auth/me")).status_code == 401


@pytest.mark.anyio
async def test_share_view_download_and_revocation(tmp_path: Path) -> None:
    settings = Settings(
        "test-only-secret-key-with-more-than-32-bytes",
        tmp_path / "sharing.sqlite3",
        tmp_path / "shared-files",
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport_owner = httpx.ASGITransport(app=app)
        transport_recipient = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport_owner, base_url="http://test") as owner, \
                   httpx.AsyncClient(transport=transport_recipient, base_url="http://test") as recipient:
            await register(owner, "owner@example.com")
            await register(recipient, "reader@example.com")
            uploaded = await owner.post(
                "/api/documents", files={"file": ("shared.txt", b"shared content", "text/plain")},
            )
            document_id = uploaded.json()["id"]

            created = await owner.post(
                f"/api/documents/{document_id}/shares", json={"email": "reader@example.com"},
            )
            assert created.status_code == 201, created.text
            assert created.json()["email"] == "reader@example.com"
            assert (await owner.get(f"/api/documents/{document_id}/shares")).status_code == 200

            shared_document = (await recipient.get("/api/documents")).json()[0]
            assert shared_document["id"] == document_id
            assert shared_document["is_owner"] is False
            assert shared_document["shared_by"] == "owner"
            view = await recipient.get(f"/api/documents/{document_id}/view")
            assert view.status_code == 200
            assert view.content == b"shared content"
            assert view.headers["content-disposition"].startswith("inline;")
            download = await recipient.get(f"/api/documents/{document_id}/download")
            assert download.status_code == 200
            assert download.content == b"shared content"
            assert (await recipient.get(f"/api/documents/{document_id}/shares")).status_code == 404

            revoked = await owner.delete(
                f"/api/documents/{document_id}/shares/{created.json()['id']}",
            )
            assert revoked.status_code == 204
            assert (await recipient.get("/api/documents")).json() == []
            assert (await recipient.get(f"/api/documents/{document_id}/download")).status_code == 404
            owner_events = {item["event_type"] for item in (await owner.get("/api/audit")).json()}
            assert {"document_shared", "document_access_revoked"} <= owner_events


@pytest.mark.anyio
async def test_admin_can_manage_regular_accounts_but_users_cannot(tmp_path: Path) -> None:
    settings = Settings(
        "test-only-secret-key-with-more-than-32-bytes",
        tmp_path / "admin.sqlite3",
        tmp_path / "admin-files",
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as admin, \
                   httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as regular, \
                   httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as another_admin_client:
            admin_user = await register(admin, "admin@example.com")
            regular_user = await register(regular, "regular@example.com")
            another_admin = await register(another_admin_client, "another-admin@example.com")
            with connect(settings.database_path) as db:
                db.executemany(
                    "UPDATE users SET role = 'admin' WHERE id = ?",
                    [(admin_user["id"],), (another_admin["id"],)],
                )

            forbidden = await regular.get("/api/admin/users")
            assert forbidden.status_code == 403

            listing = await admin.get("/api/admin/users")
            assert listing.status_code == 200
            assert {item["email"] for item in listing.json()} == {
                "admin@example.com", "another-admin@example.com", "regular@example.com",
            }
            managed_user = next(item for item in listing.json() if item["email"] == "regular@example.com")
            disabled = await admin.patch(
                f"/api/admin/users/{regular_user['id']}", json={"is_active": False},
            )
            assert disabled.status_code == 200
            assert disabled.json()["is_active"] is False
            assert (await regular.get("/api/auth/me")).status_code == 401
            rejected_login = await regular.post(
                "/api/auth/login",
                json={"email": "regular@example.com", "password": "correct horse battery staple"},
            )
            assert rejected_login.status_code == 403

            enabled = await admin.patch(
                f"/api/admin/users/{regular_user['id']}", json={"is_active": True},
            )
            assert enabled.status_code == 200
            assert (await regular.get("/api/auth/me")).status_code == 200
            cannot_disable_self = await admin.patch(
                f"/api/admin/users/{admin_user['id']}", json={"is_active": False},
            )
            assert cannot_disable_self.status_code == 400
            cannot_disable_other_admin = await admin.patch(
                f"/api/admin/users/{another_admin['id']}", json={"is_active": False},
            )
            assert cannot_disable_other_admin.status_code == 400
            assert managed_user["role"] == "user"


def test_database_migrates_existing_users_table(tmp_path: Path) -> None:
    database_path = tmp_path / "old-schema.sqlite3"
    with connect(database_path) as db:
        db.execute(
            "CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, "
            "display_name TEXT NOT NULL, password_hash TEXT NOT NULL, created_at TEXT NOT NULL)"
        )
        db.execute(
            "INSERT INTO users(id, email, display_name, password_hash, created_at) "
            "VALUES ('existing-id', 'existing@example.com', 'Existing', 'hash', '2026-01-01')"
        )
    from app.database import initialize_database

    initialize_database(database_path)
    with connect(database_path) as db:
        row = db.execute("SELECT role, is_active FROM users WHERE id = 'existing-id'").fetchone()
    assert row["role"] == "user"
    assert row["is_active"] == 1
