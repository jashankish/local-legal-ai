"""Watched-folder ingestion: drop files into the inbox and they are indexed automatically.

Layout (relative to INBOX_DIR, default data/inbox):
    inbox/                      files here get category "general"
    inbox/<category>/           files here get that category, e.g. inbox/contracts/
    inbox/processed/YYYY-MM-DD/ successfully indexed files are moved here
    inbox/failed/               rejected files, each with a <name>.error.txt explanation

A file is only picked up once its size and modification time have been stable
for one full scan, so large copies from a scanner or network share are not
read half-written.
"""

import logging
import os
import shutil
import threading
import time
from collections import deque
from datetime import datetime
from typing import Any, Callable, Deque, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}
RESERVED_DIRS = {"processed", "failed"}


class FolderWatcher:
    """Polling watcher (portable across macOS, Linux, Windows and network shares)."""

    def __init__(self, inbox_dir: str, ingest: Callable[..., Dict[str, Any]],
                 interval_seconds: float = 10.0, uploaded_by: str = "inbox",
                 on_failure: Optional[Callable[[str, str, str], None]] = None):
        self.inbox_dir = os.path.abspath(inbox_dir)
        self.ingest = ingest
        self.on_failure = on_failure  # (filename, category, error) for audit/notifications
        self.interval = max(1.0, interval_seconds)
        self.uploaded_by = uploaded_by
        self.history: Deque[Dict[str, Any]] = deque(maxlen=50)
        self.stats = {"processed": 0, "failed": 0, "last_scan": None, "running": False}
        self._seen: Dict[str, Tuple[int, float]] = {}
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._scan_lock = threading.Lock()
        for sub in ("", "processed", "failed"):
            os.makedirs(os.path.join(self.inbox_dir, sub), exist_ok=True)

    # -- lifecycle ---------------------------------------------------------------------
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="inbox-watcher", daemon=True)
        self._thread.start()
        self.stats["running"] = True
        logger.info(f"Inbox watcher started on {self.inbox_dir} (every {self.interval:.0f}s)")

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.interval + 5)
        self.stats["running"] = False

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.scan_once()
            except Exception as e:  # never let the thread die
                logger.error(f"Inbox scan failed: {e}")
            self._stop.wait(self.interval)

    # -- scanning ----------------------------------------------------------------------
    def _candidates(self):
        for root, dirs, files in os.walk(self.inbox_dir):
            rel = os.path.relpath(root, self.inbox_dir)
            top = rel.split(os.sep)[0]
            if top in RESERVED_DIRS:
                dirs[:] = []
                continue
            dirs[:] = [d for d in dirs if not d.startswith(".") and (rel != "." or d not in RESERVED_DIRS)]
            for name in files:
                if name.startswith(".") or name.startswith("~$"):
                    continue  # hidden files and Office lock files
                category = "general" if rel == "." else top
                yield os.path.join(root, name), category

    def scan_once(self, require_stable: bool = True) -> Dict[str, int]:
        """Process every stable file currently in the inbox. Returns counts for this scan."""
        counts = {"processed": 0, "failed": 0, "waiting": 0}
        with self._scan_lock:
            present = set()
            for path, category in self._candidates():
                present.add(path)
                try:
                    stat = os.stat(path)
                except FileNotFoundError:
                    continue
                signature = (stat.st_size, stat.st_mtime)
                if require_stable and self._seen.get(path) != signature:
                    self._seen[path] = signature
                    counts["waiting"] += 1
                    continue
                self._seen.pop(path, None)
                counts["processed" if self._process(path, category) else "failed"] += 1
            # forget files that vanished before they stabilised
            for path in list(self._seen):
                if path not in present:
                    self._seen.pop(path)
            self.stats["last_scan"] = datetime.now().isoformat(timespec="seconds")
        return counts

    def _process(self, path: str, category: str) -> bool:
        name = os.path.basename(path)
        record = {"file": name, "category": category, "timestamp": datetime.now().isoformat(timespec="seconds")}
        ext = os.path.splitext(name)[1].lower()
        try:
            if ext not in SUPPORTED_EXTENSIONS:
                raise ValueError(f"Unsupported file type '{ext or 'none'}'; use PDF, DOCX or TXT")
            with open(path, "rb") as f:
                content = f.read()
            title = os.path.splitext(name)[0].replace("_", " ").strip() or name
            result = self.ingest(content, name, self.uploaded_by, title, category, None, "inbox")
            destination = self._move(path, os.path.join("processed", datetime.now().strftime("%Y-%m-%d")))
            record.update(ok=True, document_id=result.get("document_id"),
                          passages=result.get("chunks_processed"), moved_to=destination)
            self.stats["processed"] += 1
            logger.info(f"Inbox: indexed {name} as {result.get('document_id')}")
            return True
        except Exception as e:
            error = getattr(e, "detail", None) or str(e)
            destination = self._move(path, "failed")
            with open(os.path.join(self.inbox_dir, destination) + ".error.txt", "w") as f:
                f.write(f"{datetime.now().isoformat(timespec='seconds')}\n{error}\n")
            record.update(ok=False, error=error, moved_to=destination)
            self.stats["failed"] += 1
            logger.warning(f"Inbox: could not index {name}: {error}")
            if self.on_failure:
                self.on_failure(name, category, error)
            return False
        finally:
            self.history.appendleft(record)

    def _move(self, path: str, subdir: str) -> str:
        """Move into inbox/<subdir>/, avoiding name clashes. Returns the inbox-relative path."""
        target_dir = os.path.join(self.inbox_dir, subdir)
        os.makedirs(target_dir, exist_ok=True)
        base, ext = os.path.splitext(os.path.basename(path))
        target = os.path.join(target_dir, base + ext)
        counter = 1
        while os.path.exists(target):
            target = os.path.join(target_dir, f"{base} ({counter}){ext}")
            counter += 1
        shutil.move(path, target)
        return os.path.relpath(target, self.inbox_dir)

    def status(self) -> Dict[str, Any]:
        waiting = sum(1 for _ in self._candidates())
        # Show the configured, project-relative path rather than the absolute
        # server path (which exposes home directories in the UI).
        relative = os.path.relpath(self.inbox_dir, os.getcwd())
        display_dir = self.inbox_dir if relative.startswith("..") else relative
        return {**self.stats, "inbox_dir": display_dir, "interval_seconds": self.interval,
                "waiting": waiting, "recent": list(self.history)[:20]}
