"""End-to-end API tests: auth, document lifecycle and RAG answers."""

SAMPLE_CONTRACT = """MASTER SERVICES AGREEMENT

This Master Services Agreement is entered into between Acme Corporation ("Client") and Northwind LLP ("Provider").

Section 1. Services. Provider shall deliver document review services described in each Statement of Work.

Section 2. Fees. Client shall pay Provider a monthly retainer of $15,000, invoiced on the first business day of each month. Late payments accrue interest at 1.5% per month.

Section 3. Termination. Either party may terminate this Agreement upon sixty (60) days written notice to the other party. Client may terminate immediately for material breach that remains uncured after thirty (30) days.

Section 4. Confidentiality. Each party shall keep confidential all proprietary information disclosed under this Agreement for a period of five (5) years following termination.

Section 5. Governing Law. This Agreement is governed by the laws of the State of New York.
"""


def upload(client, headers, name="msa.txt", text=SAMPLE_CONTRACT, category="contracts"):
    return client.post(
        "/documents/upload",
        headers=headers,
        files={"file": (name, text.encode(), "text/plain")},
        data={"title": name, "category": category},
    )


def test_health_reports_services(client):
    body = client.get("/health").json()
    assert body["status"] == "healthy"
    assert body["services"]["chromadb"] == "healthy"
    assert body["services"]["model"] == "not_configured"


def test_bad_credentials_return_401(client):
    response = client.post("/auth/login", json={"username": "admin", "password": "wrong"})
    assert response.status_code == 401


def test_protected_routes_require_token(client):
    assert client.get("/documents").status_code in (401, 403)


def test_document_lifecycle_and_extractive_query(client, admin_headers):
    response = upload(client, admin_headers)
    body = response.json()
    assert body["success"], body
    document_id = body["document_id"]
    assert body["chunks_processed"] >= 1

    listing = client.get("/documents", headers=admin_headers).json()
    entry = next(d for d in listing["documents"] if d["id"] == document_id)
    assert entry["filename"] == "msa.txt"
    assert entry["category"] == "contracts"
    assert entry["chunk_count"] == body["chunks_processed"]

    answer = client.post(
        "/query", headers=admin_headers,
        json={"question": "What notice period is required to terminate the agreement?"},
    ).json()
    assert answer["mode"] == "extractive"
    assert "sixty (60) days" in answer["answer"]
    assert answer["citations"], "extractive answers should cite their sources"
    assert answer["sources"][0]["document_id"] == document_id
    assert 0.0 <= answer["confidence_score"] <= 1.0

    deleted = client.delete(f"/documents/{document_id}", headers=admin_headers)
    assert deleted.status_code == 200
    assert deleted.json()["chunks_deleted"] == body["chunks_processed"]
    remaining = client.get("/documents", headers=admin_headers).json()["documents"]
    assert all(d["id"] != document_id for d in remaining)


def test_delete_unknown_document_returns_404(client, admin_headers):
    assert client.delete("/documents/does-not-exist", headers=admin_headers).status_code == 404


def test_empty_upload_rejected(client, admin_headers):
    assert upload(client, admin_headers, text="").status_code == 400


def test_generative_answer_when_llm_available(client, admin_headers, monkeypatch):
    from rag.rag_pipeline import get_rag_pipeline

    llm = get_rag_pipeline().llm

    async def fake_status(force=False):
        return {"available": True, "state": "healthy"}

    async def fake_chat(messages):
        prompt = messages[-1]["content"]
        assert "[1]" in prompt and "QUESTION:" in prompt
        return "The monthly retainer is $15,000 [1].", 42, "test-model"

    monkeypatch.setattr(llm, "status", fake_status)
    monkeypatch.setattr(llm, "chat", fake_chat)

    document_id = upload(client, admin_headers, name="fees.txt").json()["document_id"]
    answer = client.post(
        "/documents/query", headers=admin_headers,
        json={"query": "What is the monthly retainer?", "max_results": 3},
    ).json()
    assert answer["mode"] == "generative"
    assert answer["model"] == "test-model"
    assert answer["citations"] == [1]
    assert "$15,000" in answer["answer"]
    client.delete(f"/documents/{document_id}", headers=admin_headers)
