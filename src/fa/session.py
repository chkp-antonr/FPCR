"""Session management with SQLite storage."""

import dataclasses
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path

from cryptography.fernet import Fernet

from .config import settings


@dataclasses.dataclass
class SessionData:
    """Session data stored in database."""

    username: str
    password: str  # Decrypted password for CP API calls
    created_at: datetime
    last_accessed: datetime


class SessionManager:
    """Manages user sessions with SQLite storage."""

    def __init__(self, db_path: str | None = None):
        """Initialize session manager with SQLite database.

        If db_path is None, uses the path from DATABASE_URL config.
        """
        if db_path is None:
            db_path = settings.sqlite_db_path
        self.db_path = Path(db_path)
        self._cipher = Fernet(settings.secret_key.encode())
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        """Create sessions table if not exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            conn = self._get_connection()
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    password_encrypted TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_accessed TEXT NOT NULL
                )
            """
            )
            conn.commit()
            conn.close()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def create(self, username: str, password: str) -> str:
        """Create a new session and return session ID."""
        session_id = secrets.token_urlsafe(32)
        password_encrypted = self._cipher.encrypt(password.encode()).decode()
        now = datetime.now().isoformat()

        with self._lock:
            conn = self._get_connection()
            conn.execute(
                "INSERT INTO sessions (session_id, username, password_encrypted, created_at, last_accessed) VALUES (?, ?, ?, ?, ?)",
                (session_id, username, password_encrypted, now, now),
            )
            conn.commit()
            conn.close()
        return session_id

    def get(self, session_id: str) -> SessionData | None:
        """Get session data if valid and not expired."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.execute(
                "SELECT username, password_encrypted, created_at, last_accessed FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            row = cursor.fetchone()
            conn.close()

        if not row:
            return None

        username, password_encrypted, created_at_str, last_accessed_str = row

        # Check expiry
        last_accessed = datetime.fromisoformat(last_accessed_str)
        if datetime.now() - last_accessed > timedelta(hours=settings.session_age_hours):
            self.delete(session_id)
            return None

        # Avoid a write on every poll-heavy request; once per minute is enough.
        if datetime.now() - last_accessed > timedelta(minutes=1):
            with self._lock:
                conn = self._get_connection()
                try:
                    conn.execute(
                        "UPDATE sessions SET last_accessed = ? WHERE session_id = ?",
                        (datetime.now().isoformat(), session_id),
                    )
                    conn.commit()
                except sqlite3.OperationalError as e:
                    # If database is locked, skip the update and just return the session.
                    # The session is still valid; we just skip updating the timestamp.
                    if "locked" not in str(e).lower():
                        raise
                finally:
                    conn.close()

        # Decrypt password
        password = self._cipher.decrypt(password_encrypted.encode()).decode()

        return SessionData(
            username=username,
            password=password,
            created_at=datetime.fromisoformat(created_at_str),
            last_accessed=last_accessed,
        )

    def delete(self, session_id: str) -> None:
        """Delete a session."""
        with self._lock:
            conn = self._get_connection()
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            conn.commit()
            conn.close()

    def cleanup_expired(self) -> int:
        """Delete all expired sessions, return count deleted."""
        expiry_cutoff = (datetime.now() - timedelta(hours=settings.session_age_hours)).isoformat()
        with self._lock:
            conn = self._get_connection()
            cursor = conn.execute("DELETE FROM sessions WHERE last_accessed < ?", (expiry_cutoff,))
            deleted = cursor.rowcount
            conn.commit()
            conn.close()
        return deleted


# Global session manager instance — uses the same database as the cache (DATABASE_URL)
session_manager = SessionManager()
