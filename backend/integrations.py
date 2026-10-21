"""Outbound event notifications for automation (n8n) and chat alerts (Slack).

Audit actions are mapped to a small set of public event names and delivered
from a background thread so a slow or unreachable webhook never delays a
request. Only metadata is sent — document text and question text never leave
the machine through this channel.

n8n payloads are signed with HMAC-SHA256 over the raw JSON body when
WEBHOOK_SECRET is set, in the header ``X-LegalAI-Signature: sha256=<hex>``.
"""

import hashlib
import hmac
import json
import logging
import queue
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, Iterable, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

# (audit action, outcome) -> public event name. Queries are deliberately absent.
EVENT_MAP: Dict[Tuple[str, str], str] = {
    ("document.upload", "success"): "document.indexed",
    ("document.upload", "failure"): "document.ingest_failed",
    ("document.delete", "success"): "document.deleted",
    ("auth.login", "failure"): "security.login_failed",
    ("auth.login", "denied"): "security.login_denied",
    ("auth.login", "locked"): "security.login_locked",
    ("access.ip_denied", "denied"): "security.ip_denied",
    ("audit.verify", "failure"): "security.audit_tamper_detected",
    ("user.create", "success"): "user.created",
    ("user.update", "success"): "user.updated",
    ("user.password_reset", "success"): "user.password_reset",
    ("integration.test", "success"): "integration.test",
}
ALL_EVENTS = sorted(set(EVENT_MAP.values()))
# Detail keys that may carry privileged content and are never forwarded.
REDACTED_DETAIL_KEYS = {"question", "content", "text", "answer"}

SLACK_TEMPLATES = {
    "document.indexed": ":page_facing_up: *{title}* indexed by {actor} — {chunks} passages ({category}, via {channel})",
    "document.ingest_failed": ":warning: Could not index *{filename}* (via {channel}): {error}",
    "document.deleted": ":wastebasket: *{filename}* deleted by {actor}",
    "security.login_failed": ":closed_lock_with_key: Failed sign-in for *{actor}* from {ip}",
    "security.login_denied": ":no_entry: Sign-in attempt on disabled account *{actor}* from {ip}",
    "security.login_locked": ":lock: Sign-in for *{actor}* from {ip} blocked after repeated failures",
    "security.ip_denied": ":no_entry_sign: Request from non-allowed address {ip} to {resource}",
    "security.audit_tamper_detected": ":rotating_light: Audit log integrity check FAILED at event #{first_invalid_id}",
    "user.created": ":bust_in_silhouette: {actor} added user *{resource}* ({role})",
    "user.updated": ":pencil2: {actor} updated user *{resource}*",
    "user.password_reset": ":key: {actor} reset the password for *{resource}*",
    "integration.test": ":white_check_mark: Test notification from Local Legal AI (sent by {actor})",
}


class _SafeDict(dict):
    def __missing__(self, key):
        return "—"


def sign_payload(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def verify_signature(body: bytes, secret: str, header: str) -> bool:
    """Helper for receivers (and tests) to check X-LegalAI-Signature."""
    return hmac.compare_digest(sign_payload(body, secret), header or "")


class EventNotifier:
    """Queue-backed webhook sender with retries and a short delivery history."""

    def __init__(self, n8n_url: Optional[str] = None, slack_url: Optional[str] = None,
                 secret: Optional[str] = None, events: Optional[Iterable[str]] = None,
                 instance_name: str = "Local Legal AI", timeout: float = 5.0, retries: int = 3):
        self.configure(n8n_url, slack_url, secret, events)
        self.instance_name = instance_name
        self.timeout = timeout
        self.retries = retries
        self.history: Deque[Dict[str, Any]] = deque(maxlen=50)
        self._queue: "queue.Queue[Optional[Tuple[str, Dict[str, Any]]]]" = queue.Queue(maxsize=1000)
        self._worker: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def configure(self, n8n_url=None, slack_url=None, secret=None, events=None):
        self.n8n_url = (n8n_url or "").strip() or None
        self.slack_url = (slack_url or "").strip() or None
        self.secret = (secret or "").strip() or None
        selected = [e.strip() for e in (events or []) if e and e.strip()]
        self.events = set(selected) if selected else set(ALL_EVENTS)

    @property
    def enabled(self) -> bool:
        return bool(self.n8n_url or self.slack_url)

    # -- producer side -----------------------------------------------------------------
    def build_event(self, action: str, status: str, actor: Optional[str], resource: Optional[str],
                    details: Optional[Dict[str, Any]], ip: Optional[str]) -> Optional[Dict[str, Any]]:
        name = EVENT_MAP.get((action, status))
        if name is None or name not in self.events:
            return None
        safe_details = {k: v for k, v in (details or {}).items() if k not in REDACTED_DETAIL_KEYS}
        return {
            "event": name,
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": self.instance_name,
            "actor": actor,
            "resource": resource,
            "status": status,
            "ip": ip,
            "details": safe_details,
        }

    def notify_action(self, action: str, status: str = "success", actor: Optional[str] = None,
                      resource: Optional[str] = None, details: Optional[Dict[str, Any]] = None,
                      ip: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Translate an audit action into an event and enqueue it for delivery."""
        if not self.enabled:
            return None
        event = self.build_event(action, status, actor, resource, details, ip)
        if event is None:
            return None
        self._ensure_worker()
        try:
            self._queue.put_nowait(("event", event))
        except queue.Full:
            logger.warning(f"Notification queue full; dropping {event['event']}")
            return None
        return event

    # -- consumer side -----------------------------------------------------------------
    def _ensure_worker(self):
        with self._lock:
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._run, name="event-notifier", daemon=True)
                self._worker.start()

    def _run(self):
        while True:
            item = self._queue.get()
            if item is None:
                self._queue.task_done()
                return
            _, event = item
            try:
                self.deliver(event)
            finally:
                self._queue.task_done()

    def flush(self, timeout: float = 10.0) -> bool:
        """Wait until queued events have been attempted (used by tests and shutdown)."""
        deadline = time.time() + timeout
        while self._queue.unfinished_tasks and time.time() < deadline:
            time.sleep(0.05)
        return self._queue.unfinished_tasks == 0

    def stop(self):
        if self._worker and self._worker.is_alive():
            self._queue.put(None)
            self._worker.join(timeout=5)

    def deliver(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Send one event to every configured target synchronously; returns delivery records."""
        records = []
        if self.n8n_url:
            body = json.dumps(event, sort_keys=True, default=str).encode("utf-8")
            headers = {"Content-Type": "application/json", "User-Agent": "LocalLegalAI-Webhook/1.0"}
            if self.secret:
                headers["X-LegalAI-Signature"] = sign_payload(body, self.secret)
            records.append(self._post("n8n", self.n8n_url, body, headers, event))
        if self.slack_url:
            body = json.dumps({"text": self.slack_text(event)}).encode("utf-8")
            records.append(self._post("slack", self.slack_url, body, {"Content-Type": "application/json"}, event))
        return records

    def _post(self, target: str, url: str, body: bytes, headers: Dict[str, str],
              event: Dict[str, Any]) -> Dict[str, Any]:
        record = {"event": event["event"], "target": target, "timestamp": event["timestamp"],
                  "ok": False, "status_code": None, "attempts": 0, "error": None}
        for attempt in range(1, self.retries + 1):
            record["attempts"] = attempt
            try:
                response = httpx.post(url, content=body, headers=headers, timeout=self.timeout)
                record["status_code"] = response.status_code
                if response.status_code < 300:
                    record["ok"] = True
                    record["error"] = None
                    break
                record["error"] = f"HTTP {response.status_code}"
                if response.status_code < 500 and response.status_code != 429:
                    break  # client errors won't succeed on retry
            except httpx.HTTPError as e:
                record["error"] = type(e).__name__
            time.sleep(0.5 * attempt)
        if not record["ok"]:
            logger.warning(f"Webhook delivery to {target} failed for {event['event']}: {record['error']}")
        self.history.appendleft(record)
        return record

    @staticmethod
    def slack_text(event: Dict[str, Any]) -> str:
        details = event.get("details") or {}
        values = _SafeDict({**details, **{k: v for k, v in event.items() if k != "details" and v is not None}})
        values.setdefault("title", details.get("title") or details.get("filename") or event.get("resource"))
        template = SLACK_TEMPLATES.get(event["event"], "{event}: {resource}")
        return template.format_map(values)

    def status(self) -> Dict[str, Any]:
        def mask(url):
            if not url:
                return None
            return url.split("//", 1)[-1].split("/", 1)[0] + "/…"
        return {
            "enabled": self.enabled,
            "n8n": {"configured": bool(self.n8n_url), "target": mask(self.n8n_url), "signed": bool(self.secret)},
            "slack": {"configured": bool(self.slack_url), "target": mask(self.slack_url)},
            "events": sorted(self.events),
            "available_events": ALL_EVENTS,
            "pending": self._queue.unfinished_tasks,
            "recent_deliveries": list(self.history)[:20],
        }
