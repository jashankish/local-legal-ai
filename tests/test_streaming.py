"""Token streaming from an OpenAI-compatible server, end to end over HTTP."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from tests.test_api import upload

FRAGMENTS = ["Either party ", "may terminate ", "on sixty (60) days ", "written notice [1]."]


class _FakeModelServer(BaseHTTPRequestHandler):
    """Minimal vLLM/Ollama stand-in: /v1/models and streaming /v1/chat/completions."""
    fail_after = None  # emit this many fragments, then drop the connection
    requests = []

    def do_GET(self):
        body = json.dumps({"data": [{"id": "fake-legal-model"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).requests.append(payload)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for index, text in enumerate(FRAGMENTS):
            if self.fail_after is not None and index == self.fail_after:
                self.wfile.flush()
                self.connection.close()
                return
            chunk = {"model": "fake-legal-model", "choices": [{"index": 0, "delta": {"content": text}}]}
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
            self.wfile.flush()
        usage = {"model": "fake-legal-model", "choices": [], "usage": {"total_tokens": 57}}
        self.wfile.write(f"data: {json.dumps(usage)}\n\ndata: [DONE]\n\n".encode())

    def log_message(self, *args):
        pass


@pytest.fixture()
def model_server(client, monkeypatch):
    import rag.rag_pipeline as pipeline_module

    _FakeModelServer.fail_after = None
    _FakeModelServer.requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeModelServer)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    llm = pipeline_module.get_rag_pipeline().llm
    monkeypatch.setattr(pipeline_module.settings, "llm_enabled", True)
    monkeypatch.setattr(llm, "endpoint", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setattr(llm, "_status_cache", (0.0, {}))
    yield _FakeModelServer
    llm._status_cache = (0.0, {})
    server.shutdown()


def read_events(response):
    return [json.loads(line) for line in response.iter_lines() if line]


def test_stream_endpoint_emits_sources_tokens_and_result(client, admin_headers, model_server):
    document_id = upload(client, admin_headers, name="stream-msa.txt").json()["document_id"]
    with client.stream("POST", "/query/stream", headers=admin_headers,
                       json={"question": "How can the agreement be terminated?", "num_documents": 3}) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/x-ndjson")
        events = read_events(response)

    assert events[0]["type"] == "sources" and events[0]["sources"][0]["document_id"] == document_id
    tokens = [e["text"] for e in events if e["type"] == "token"]
    assert tokens == FRAGMENTS, "each model fragment is forwarded as it arrives"
    done = events[-1]
    assert done["type"] == "done"
    result = done["result"]
    assert result["mode"] == "generative"
    assert result["model"] == "fake-legal-model"
    assert result["total_tokens_used"] == 57
    assert result["answer"] == "".join(FRAGMENTS)
    assert result["citations"] == [1]
    assert "sixty (60) days" in result["legal_entities"]["durations"]

    sent = model_server.requests[-1]
    assert sent["stream"] is True and sent["messages"][0]["role"] == "system"
    client.delete(f"/documents/{document_id}", headers=admin_headers)


def test_non_streaming_query_uses_the_same_model_path(client, admin_headers, model_server):
    document_id = upload(client, admin_headers, name="stream-msa-2.txt").json()["document_id"]
    answer = client.post("/query", headers=admin_headers,
                         json={"question": "How can the agreement be terminated?"}).json()
    assert answer["mode"] == "generative" and answer["answer"] == "".join(FRAGMENTS)
    client.delete(f"/documents/{document_id}", headers=admin_headers)


def test_model_dropping_mid_answer_keeps_partial_text_with_notice(client, admin_headers, model_server):
    model_server.fail_after = 2
    document_id = upload(client, admin_headers, name="stream-msa-3.txt").json()["document_id"]
    with client.stream("POST", "/query/stream", headers=admin_headers,
                       json={"question": "How can the agreement be terminated?"}) as response:
        events = read_events(response)
    result = events[-1]["result"]
    assert result["answer"].startswith("".join(FRAGMENTS[:2]).strip())
    assert result["mode"] == "generative"
    assert "may be incomplete" in result["answer"]
    client.delete(f"/documents/{document_id}", headers=admin_headers)


def test_extractive_answers_stream_too(client, admin_headers):
    document_id = upload(client, admin_headers, name="stream-msa-4.txt").json()["document_id"]
    with client.stream("POST", "/query/stream", headers=admin_headers,
                       json={"question": "What notice period is required to terminate?"}) as response:
        events = read_events(response)
    tokens = [e for e in events if e["type"] == "token"]
    assert len(tokens) > 1, "extractive answers are emitted passage by passage"
    assert events[-1]["result"]["mode"] == "extractive"
    assert "".join(t["text"] for t in tokens).strip() == events[-1]["result"]["answer"].strip()
    client.delete(f"/documents/{document_id}", headers=admin_headers)


def test_uncited_model_sentences_are_attributed_only_on_strong_overlap(client):
    from rag.rag_pipeline import RetrievalResult, get_rag_pipeline

    pipeline = get_rag_pipeline()
    sources = [
        RetrievalResult("a", "Section 8. Early Termination. Tenant may terminate this Lease effective on the "
                             "last day of the thirty-sixth (36th) month by giving Landlord at least nine (9) "
                             "months prior written notice and paying a termination fee equal to four (4) "
                             "months of then-current base rent.", {}, 0.9, 0),
        RetrievalResult("b", "Section 3. Base Rent. Tenant shall pay base rent of $18,900 per month.", {}, 0.5, 1),
    ]
    answer = ("The tenant can terminate the lease at the end of the thirty-sixth (36th) month. "
              "They must give nine (9) months prior written notice and pay a termination fee of four (4) "
              "months of base rent. This is generally favourable. Base rent is $18,900 per month [2].")
    attributed = pipeline._attribute_uncited_sentences(answer, sources)
    assert "thirty-sixth (36th) month [1]." in attributed
    assert "base rent [1]." in attributed
    assert "This is generally favourable." in attributed and "favourable. [" not in attributed
    assert attributed.count("[2]") == 1, "existing citations are left alone"


def test_off_topic_questions_never_reach_the_model(client, admin_headers, model_server):
    document_id = upload(client, admin_headers, name="stream-msa-5.txt").json()["document_id"]
    calls_before = len(model_server.requests)
    answer = client.post("/query", headers=admin_headers,
                         json={"question": "What is the capital of France?"}).json()
    assert answer["mode"] == "no_match"
    assert "None of your documents" in answer["answer"]
    assert len(model_server.requests) == calls_before, "the model must not answer from general knowledge"
    assert answer["sources"], "closest passages are still shown"
    client.delete(f"/documents/{document_id}", headers=admin_headers)


def test_uncited_generated_answers_carry_a_caution(client, admin_headers, model_server, monkeypatch):
    monkeypatch.setattr("tests.test_streaming.FRAGMENTS", ["It depends on many factors."])
    document_id = upload(client, admin_headers, name="stream-msa-6.txt").json()["document_id"]
    answer = client.post("/query", headers=admin_headers,
                         json={"question": "How can the agreement be terminated?"}).json()
    assert answer["mode"] == "generative" and answer["citations"] == []
    assert "check it against the sources" in answer["answer"]
    client.delete(f"/documents/{document_id}", headers=admin_headers)


def test_stream_requires_auth_and_a_question(client, admin_headers):
    assert client.post("/query/stream", json={"question": "x"}).status_code in (401, 403)
    assert client.post("/query/stream", headers=admin_headers, json={"question": "  "}).status_code == 400
