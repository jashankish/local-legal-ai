"""Tamper-evident audit trail for logins, document access and queries.

Each event is stored in SQLite with a SHA-256 hash that covers the event's
fields and the previous event's hash. Editing or deleting any stored row breaks
the chain, which `verify_chain()` detects — useful when a firm has to show who
accessed which client documents and when.
"""

import contextvars
import csv
import hashlib
import io
import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

GENESIS_HASH = "0" * 64

# Populated per request by the API middleware so call sites don't have to
# thread the client address through every function.
request_context: contextvars.ContextVar[Dict[str, str]] = contextvars.ContextVar(
    "audit_request_context", default={}
)

HASHED_FIELDS = ("timestamp", "username", "action", "resource", "status", "ip_address", "user_agent", "details")


class AuditLogger:
    """Append-only, hash-chained audit log backed by SQLite."""

    def __init__(self, db_path: str = "data/audit.db", enabled: bool = True):
        self.db_path = db_path
        self.enabled = enabled
        self._lock = threading.Lock()
        directory = os.path.dirname(db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self._init_database()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_database(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    username TEXT,
                    action TEXT NOT NULL,
                    resource TEXT,
                    status TEXT NOT NULL,
                    ip_address TEXT,
                    user_agent TEXT,
                    details TEXT,
                    prev_hash TEXT NOT NULL,
                    hash TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_events(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_events(username)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_events(action)")

    @staticmethod
    def _compute_hash(prev_hash: str, event: Dict[str, Any]) -> str:
        payload = json.dumps({k: event.get(k) for k in HASHED_FIELDS}, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256((prev_hash + payload).encode("utf-8")).hexdigest()

    def record(self,
               action: str,
               username: Optional[str] = None,
               status: str = "success",
               resource: Optional[str] = None,
               details: Optional[Dict[str, Any]] = None,
               ip_address: Optional[str] = None,
               user_agent: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Append an event. Failures are logged, never raised, so auditing cannot break requests."""
        if not self.enabled:
            return None
        context = request_context.get()
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "username": username,
            "action": action,
            "resource": resource,
            "status": status,
            "ip_address": ip_address or context.get("ip"),
            "user_agent": (user_agent or context.get("user_agent") or "")[:300] or None,
            "details": json.dumps(details, sort_keys=True, default=str) if details else None,
        }
        try:
            with self._lock, self._connect() as conn:
                row = conn.execute("SELECT hash FROM audit_events ORDER BY id DESC LIMIT 1").fetchone()
                prev_hash = row["hash"] if row else GENESIS_HASH
                event["prev_hash"] = prev_hash
                event["hash"] = self._compute_hash(prev_hash, event)
                cursor = conn.execute(
                    f"INSERT INTO audit_events ({', '.join(HASHED_FIELDS)}, prev_hash, hash) "
                    f"VALUES ({', '.join('?' * (len(HASHED_FIELDS) + 2))})",
                    [event[k] for k in HASHED_FIELDS] + [event["prev_hash"], event["hash"]],
                )
                event["id"] = cursor.lastrowid
            return event
        except Exception as e:
            logger.error(f"Failed to write audit event {action}: {e}")
            return None

    def _where(self, username, action, status, since_days) -> Tuple[str, List[Any]]:
        clauses, params = [], []
        if username:
            clauses.append("username = ?")
            params.append(username)
        if action:
            clauses.append("action LIKE ?")
            params.append(f"{action}%")
        if status:
            clauses.append("status = ?")
            params.append(status)
        if since_days:
            clauses.append("timestamp >= ?")
            params.append((datetime.now(timezone.utc) - timedelta(days=since_days)).isoformat())
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", params

    def query(self,
              limit: int = 100,
              offset: int = 0,
              username: Optional[str] = None,
              action: Optional[str] = None,
              status: Optional[str] = None,
              since_days: Optional[int] = None) -> Dict[str, Any]:
        """Return newest-first events matching the filters, plus the total match count."""
        where, params = self._where(username, action, status, since_days)
        with self._connect() as conn:
            total = conn.execute(f"SELECT COUNT(*) FROM audit_events{where}", params).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM audit_events{where} ORDER BY id DESC LIMIT ? OFFSET ?",
                params + [limit, offset],
            ).fetchall()
        events = []
        for row in rows:
            event = dict(row)
            event["details"] = json.loads(event["details"]) if event["details"] else None
            events.append(event)
        return {"events": events, "total": total, "limit": limit, "offset": offset}

    def summary(self, since_days: int = 30) -> Dict[str, Any]:
        """Counts by action and status for the dashboard header."""
        where, params = self._where(None, None, None, since_days)
        with self._connect() as conn:
            by_action = conn.execute(
                f"SELECT action, COUNT(*) AS n FROM audit_events{where} GROUP BY action ORDER BY n DESC", params
            ).fetchall()
            by_status = conn.execute(
                f"SELECT status, COUNT(*) AS n FROM audit_events{where} GROUP BY status", params
            ).fetchall()
        return {
            "period_days": since_days,
            "by_action": {r["action"]: r["n"] for r in by_action},
            "by_status": {r["status"]: r["n"] for r in by_status},
        }

    def verify_chain(self) -> Dict[str, Any]:
        """Recompute every hash; report the first row whose content or linkage was altered."""
        prev_hash, checked = GENESIS_HASH, 0
        with self._connect() as conn:
            for row in conn.execute("SELECT * FROM audit_events ORDER BY id ASC"):
                event = dict(row)
                if event["prev_hash"] != prev_hash or self._compute_hash(prev_hash, event) != event["hash"]:
                    return {"valid": False, "checked": checked, "first_invalid_id": event["id"]}
                prev_hash = event["hash"]
                checked += 1
        return {"valid": True, "checked": checked, "first_invalid_id": None}

    def export_csv(self, **filters) -> str:
        """Render matching events (up to 100k) as CSV for compliance review."""
        result = self.query(limit=100_000, **filters)
        buffer = io.StringIO()
        columns = ["id", *HASHED_FIELDS, "hash"]
        writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for event in reversed(result["events"]):
            event = dict(event)
            event["details"] = json.dumps(event["details"]) if event["details"] else ""
            writer.writerow(event)
        return buffer.getvalue()


_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """Process-wide audit logger configured from settings."""
    global _audit_logger
    if _audit_logger is None:
        try:
            from backend.config import settings
            enabled = settings.enable_audit_logging
        except Exception:
            enabled = True
        _audit_logger = AuditLogger(enabled=enabled)
    return _audit_logger
