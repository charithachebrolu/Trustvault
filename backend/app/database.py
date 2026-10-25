"""Small SQLite persistence layer; all queries are parameterized."""

from __future__ import annotations

import sqlite3
from pathlib import Path


class ClosingConnection(sqlite3.Connection):
    """Keep `with connect(...)` responsible for closing as well as committing."""

    def __exit__(self, exc_type, exc, traceback):
        try:
            return super().__exit__(exc_type, exc, traceback)
        finally:
            self.close()


def connect(database_path: Path) -> sqlite3.Connection:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(database_path, timeout=10, factory=ClosingConnection)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA journal_mode = WAL")
    return db


def initialize_database(database_path: Path) -> None:
    with connect(database_path) as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('user', 'admin')),
                is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1))
            );
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                original_name TEXT NOT NULL,
                storage_name TEXT NOT NULL UNIQUE,
                content_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL CHECK(size_bytes > 0),
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_documents_owner_created
                ON documents(owner_id, created_at DESC);
            CREATE TABLE IF NOT EXISTS document_shares (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                granted_by TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                can_view INTEGER NOT NULL DEFAULT 1 CHECK(can_view IN (0, 1)),
                can_download INTEGER NOT NULL DEFAULT 1 CHECK(can_download IN (0, 1)),
                expires_at TEXT,
                revoked_at TEXT,
                UNIQUE(document_id, user_id)
            );
            CREATE INDEX IF NOT EXISTS idx_document_shares_user
                ON document_shares(user_id, document_id);
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_id TEXT REFERENCES users(id) ON DELETE SET NULL,
                document_id TEXT,
                event_type TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_audit_actor_created
                ON audit_events(actor_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_audit_document_created
                ON audit_events(document_id, created_at DESC);
            """
        )
        share_columns = {row["name"] for row in db.execute("PRAGMA table_info(document_shares)")}
        if "can_view" not in share_columns:
            db.execute("ALTER TABLE document_shares ADD COLUMN can_view INTEGER NOT NULL DEFAULT 1")
        if "can_download" not in share_columns:
            db.execute("ALTER TABLE document_shares ADD COLUMN can_download INTEGER NOT NULL DEFAULT 1")
        if "expires_at" not in share_columns:
            db.execute("ALTER TABLE document_shares ADD COLUMN expires_at TEXT")
        if "revoked_at" not in share_columns:
            db.execute("ALTER TABLE document_shares ADD COLUMN revoked_at TEXT")
        user_columns = {row["name"] for row in db.execute("PRAGMA table_info(users)")}
        if "role" not in user_columns:
            db.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
        if "is_active" not in user_columns:
            db.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")


def record_event(
    db: sqlite3.Connection,
    *,
    event_type: str,
    actor_id: str | None,
    document_id: str | None = None,
    details: str = "{}",
    created_at: str,
) -> None:
    db.execute(
        "INSERT INTO audit_events(actor_id, document_id, event_type, details, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (actor_id, document_id, event_type, details, created_at),
    )
