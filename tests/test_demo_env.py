"""The local demo environment: its helpers and the event sink it ships with.

The full start/verify/stop cycle is exercised in CI (`demo.py up` → `verify` →
`down`); these are the parts worth pinning down without spawning servers.
"""

import importlib.util
import json
import os
import socket
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _load(name):
    """Import a scripts/*.py module by path (they are tools, not a package)."""
    spec = importlib.util.spec_from_file_location(name, os.path.join(REPO_ROOT, "scripts", f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


demo = _load("demo")
sink = _load("demo_event_sink")


def test_demo_uses_ports_that_do_not_clash_with_a_real_instance():
    assert demo.PORTS["api"] != 8000 and demo.PORTS["ui"] != 8501
    assert len(set(demo.PORTS.values())) == len(demo.PORTS), "every service needs its own port"


def test_secrets_are_generated_once_and_reused(tmp_path):
    paths = demo.paths(str(tmp_path))
    first = demo.load_env(paths)
    assert len(first["SECRET_KEY"]) >= 16, "must satisfy the API's own SECRET_KEY validation"

    second = demo.load_env(paths)
    assert second == first, "restarting the demo must not invalidate existing sessions"
    assert oct(os.stat(paths["env"]).st_mode)[-3:] == "600"


def test_listening_reports_a_free_port_as_closed():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        free_port = probe.getsockname()[1]
    assert demo.listening(free_port) is False


def test_model_assets_follow_the_launcher_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("LLAMA_VENV", str(tmp_path / "venv"))
    monkeypatch.setenv("MODEL_DIR", str(tmp_path / "models"))
    venv, models, ready = demo.model_assets()
    assert ready is False, "nothing downloaded yet"

    os.makedirs(os.path.join(venv, "bin"))
    open(os.path.join(venv, "bin", "python"), "w").close()
    os.makedirs(models)
    open(os.path.join(models, "model.gguf"), "w").close()
    assert demo.model_assets()[2] is True


@pytest.fixture()
def event_sink(tmp_path):
    secret = "demo-sink-secret"
    handler = sink.build_handler(str(tmp_path / "events.jsonl"), secret)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", secret, tmp_path / "events.jsonl"
    server.shutdown()


def post(url, body, headers=None):
    request = urllib.request.Request(url, data=body, method="POST",
                                     headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status


def test_event_sink_records_events_and_checks_their_signature(event_sink):
    from backend.integrations import sign_payload

    base, secret, log = event_sink
    body = json.dumps({"event": "document.indexed", "actor": "admin",
                       "details": {"filename": "msa.txt"}}).encode()

    assert post(f"{base}/n8n", body, {"X-LegalAI-Signature": sign_payload(body, secret)}) == 200
    assert post(f"{base}/n8n", body, {"X-LegalAI-Signature": "sha256=forged"}) == 200
    assert post(f"{base}/slack", json.dumps({"text": ":page_facing_up: indexed"}).encode()) == 200

    records = [json.loads(line) for line in open(log)]
    assert [r.get("signature") for r in records] == [True, False, None]
    assert records[0]["event"]["event"] == "document.indexed"
    assert records[2]["text"] == ":page_facing_up: indexed"

    with urllib.request.urlopen(f"{base}/events", timeout=5) as response:
        assert len(json.load(response)) == 3

    page = urllib.request.urlopen(base, timeout=5).read().decode()
    assert "document.indexed" in page and "SIGNATURE INVALID" in page


def test_event_sink_page_explains_itself_when_empty(event_sink):
    base, _, _ = event_sink
    assert "No events yet" in urllib.request.urlopen(base, timeout=5).read().decode()
