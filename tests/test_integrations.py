"""Webhook notifications (n8n / Slack) and watched-folder ingestion."""

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from tests.test_api import SAMPLE_CONTRACT, upload

SECRET = "integration-test-secret"


class _Receiver(BaseHTTPRequestHandler):
    received = []

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.received.append({"path": self.path, "headers": dict(self.headers), "body": body})
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture()
def webhook_receiver(client):
    from backend.app import notifier

    _Receiver.received = []
    server = HTTPServer(("127.0.0.1", 0), _Receiver)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    notifier.configure(n8n_url=f"{base}/n8n", slack_url=f"{base}/slack", secret=SECRET)
    try:
        yield _Receiver.received
    finally:
        notifier.flush()
        notifier.configure()  # disable again for other tests
        server.shutdown()


def events_for(received, target):
    return [json.loads(r["body"]) for r in received if r["path"] == f"/{target}"]


def test_upload_and_failed_login_are_delivered_signed(client, admin_headers, webhook_receiver):
    from backend.app import notifier
    from backend.integrations import verify_signature

    document_id = upload(client, admin_headers, name="notify-msa.txt").json()["document_id"]
    client.post("/auth/login", json={"username": "admin", "password": "not-the-password"})
    client.post("/query", headers=admin_headers, json={"question": "What is the monthly retainer?"})
    assert notifier.flush()

    n8n_requests = [r for r in webhook_receiver if r["path"] == "/n8n"]
    for request in n8n_requests:
        assert verify_signature(request["body"], SECRET, request["headers"]["X-LegalAI-Signature"])

    events = events_for(webhook_receiver, "n8n")
    names = [e["event"] for e in events]
    assert "document.indexed" in names and "security.login_failed" in names
    assert not any(name.startswith("query") for name in names), "questions must never be forwarded"
    indexed = next(e for e in events if e["event"] == "document.indexed")
    assert indexed["resource"] == document_id
    assert indexed["details"]["filename"] == "notify-msa.txt"

    slack_texts = [e["text"] for e in events_for(webhook_receiver, "slack")]
    assert any("indexed by admin" in text for text in slack_texts)
    assert any("Failed sign-in for *admin*" in text for text in slack_texts)

    client.delete(f"/documents/{document_id}", headers=admin_headers)


def test_test_endpoint_and_status(client, admin_headers, webhook_receiver):
    result = client.post("/integrations/test", headers=admin_headers).json()
    assert {d["target"] for d in result["deliveries"]} == {"n8n", "slack"}
    assert all(d["ok"] for d in result["deliveries"])

    status = client.get("/integrations/status", headers=admin_headers).json()
    assert status["notifications"]["n8n"]["configured"] and status["notifications"]["n8n"]["signed"]
    assert "/n8n" not in status["notifications"]["n8n"]["target"], "webhook URLs are masked"
    assert status["notifications"]["recent_deliveries"]


def test_test_endpoint_without_configuration(client, admin_headers):
    assert client.post("/integrations/test", headers=admin_headers).status_code == 400


def test_inbox_indexes_dropped_files_and_quarantines_bad_ones(client, admin_headers):
    from backend.app import inbox_watcher

    inbox = inbox_watcher.inbox_dir
    os.makedirs(os.path.join(inbox, "contracts"), exist_ok=True)
    with open(os.path.join(inbox, "contracts", "dropped_msa.txt"), "w") as f:
        f.write(SAMPLE_CONTRACT)
    with open(os.path.join(inbox, "notes.xyz"), "w") as f:
        f.write("not a supported format")

    counts = client.post("/integrations/inbox/scan", headers=admin_headers).json()["counts"]
    assert counts == {"processed": 1, "failed": 1, "waiting": 0}

    documents = client.get("/documents", headers=admin_headers).json()["documents"]
    dropped = next(d for d in documents if d["filename"] == "dropped_msa.txt")
    assert dropped["category"] == "contracts"
    assert dropped["uploaded_by"] == "inbox"
    assert dropped["source"] == "dropped msa"

    assert not os.path.exists(os.path.join(inbox, "contracts", "dropped_msa.txt"))
    processed_root = os.path.join(inbox, "processed")
    assert any("dropped_msa.txt" in files for _, _, files in os.walk(processed_root))
    assert os.path.exists(os.path.join(inbox, "failed", "notes.xyz.error.txt"))

    status = client.get("/integrations/status", headers=admin_headers).json()["inbox"]
    assert status["processed"] >= 1 and status["failed"] >= 1
    assert status["recent"][0]["file"] in {"dropped_msa.txt", "notes.xyz"}

    failures = client.get("/audit/logs", headers=admin_headers,
                          params={"action": "document.upload", "status_filter": "failure"}).json()["events"]
    assert any(e["details"].get("channel") == "inbox" for e in failures)
    client.delete(f"/documents/{dropped['id']}", headers=admin_headers)


def test_inbox_waits_for_files_to_stop_changing(client, tmp_path):
    from backend.folder_watcher import FolderWatcher

    calls = []
    watcher = FolderWatcher(str(tmp_path / "inbox"), lambda *args: calls.append(args) or {"document_id": "x"})
    path = tmp_path / "inbox" / "growing.txt"
    path.write_text("first part")
    assert watcher.scan_once()["waiting"] == 1 and not calls
    path.write_text("first part, second part")  # still being written
    assert watcher.scan_once()["waiting"] == 1 and not calls
    assert watcher.scan_once()["processed"] == 1 and len(calls) == 1


def test_integration_endpoints_require_admin(client, admin_headers):
    client.post("/auth/register", headers=admin_headers, json={
        "username": "ops-viewer", "password": "Ops-viewer-1", "role": "lawyer", "must_change_password": False})
    token = client.post("/auth/login", json={"username": "ops-viewer", "password": "Ops-viewer-1"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/integrations/status", headers=headers).status_code == 403
    assert client.post("/integrations/inbox/scan", headers=headers).status_code == 403
