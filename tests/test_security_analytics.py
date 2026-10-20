"""Audit trail, IP whitelisting and analytics backed by real activity."""

import sqlite3

from tests.test_api import SAMPLE_CONTRACT, upload

NDA_TEXT = """MUTUAL NON-DISCLOSURE AGREEMENT

Section 1. Confidential Information. Each party may disclose proprietary information and trade secrets to the other party.

Section 2. Obligations. The receiving party shall keep all Confidential Information strictly confidential for three (3) years.

Section 3. Governing Law. This Agreement is governed by the laws of the State of California.
"""


def test_login_attempts_are_audited(client, admin_headers):
    client.post("/auth/login", json={"username": "mallory", "password": "guess"})
    events = client.get("/audit/logs", headers=admin_headers,
                        params={"action": "auth.login", "username": "mallory"}).json()["events"]
    assert events and events[0]["status"] == "failure"
    assert events[0]["details"]["reason"] == "bad_credentials"
    assert events[0]["ip_address"] == "testclient"


def test_document_and_query_events_are_audited(client, admin_headers):
    document_id = upload(client, admin_headers, name="audit-msa.txt").json()["document_id"]
    client.post("/query", headers=admin_headers, json={"question": "What are the payment terms?"})
    client.delete(f"/documents/{document_id}", headers=admin_headers)

    events = client.get("/audit/logs", headers=admin_headers, params={"limit": 20}).json()["events"]
    actions = [e["action"] for e in events]
    assert {"document.upload", "query.ask", "document.delete"} <= set(actions)
    query_event = next(e for e in events if e["action"] == "query.ask")
    assert query_event["details"]["query_type"] == "Payment & Fees"


def test_audit_chain_detects_tampering(client, admin_headers):
    assert client.get("/audit/verify", headers=admin_headers).json()["valid"] is True

    from security.audit_log import get_audit_logger
    db_path = get_audit_logger().db_path
    with sqlite3.connect(db_path) as conn:
        original = conn.execute("SELECT id, username FROM audit_events ORDER BY id LIMIT 1").fetchone()
        conn.execute("UPDATE audit_events SET username = 'someone-else' WHERE id = ?", (original[0],))
    try:
        result = client.get("/audit/verify", headers=admin_headers).json()
        assert result["valid"] is False
        assert result["first_invalid_id"] == original[0]
    finally:
        with sqlite3.connect(db_path) as conn:
            conn.execute("UPDATE audit_events SET username = ? WHERE id = ?", (original[1], original[0]))
    assert client.get("/audit/verify", headers=admin_headers).json()["valid"] is True


def test_audit_export_is_csv(client, admin_headers):
    response = client.get("/audit/export", headers=admin_headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.text.splitlines()[0].startswith("id,timestamp,username,action")


def test_audit_and_analytics_require_admin(client, admin_headers):
    client.post("/auth/register", headers=admin_headers,
                json={"username": "associate", "password": "s3cret-pass", "role": "user"})
    token = client.post("/auth/login", json={"username": "associate", "password": "s3cret-pass"}).json()["access_token"]
    user_headers = {"Authorization": f"Bearer {token}"}
    for path in ("/audit/logs", "/audit/verify", "/analytics/usage", "/analytics/similarity"):
        assert client.get(path, headers=user_headers).status_code == 403, path


def test_duplicate_registration_returns_400(client, admin_headers):
    payload = {"username": "dupe-user", "password": "pw-123456", "role": "user"}
    assert client.post("/auth/register", headers=admin_headers, json=payload).status_code == 200
    assert client.post("/auth/register", headers=admin_headers, json=payload).status_code == 400


def test_ip_whitelist_blocks_unlisted_clients(client):
    from backend.auth import ip_whitelist
    ip_whitelist.configure(["10.0.0.0/8"])
    try:
        assert client.get("/health").status_code == 403  # TestClient connects as "testclient"
        assert ip_whitelist.is_allowed("10.1.2.3")
        assert not ip_whitelist.is_allowed("192.168.1.10")
    finally:
        ip_whitelist.configure([])
    assert client.get("/health").status_code == 200


def test_analytics_reflect_real_usage(client, admin_headers):
    msa_id = upload(client, admin_headers, name="analytics-msa.txt", text=SAMPLE_CONTRACT).json()["document_id"]
    nda_id = upload(client, admin_headers, name="analytics-nda.txt", text=NDA_TEXT).json()["document_id"]
    client.post("/query", headers=admin_headers, json={"question": "How can the agreement be terminated?"})

    usage = client.get("/analytics/usage", headers=admin_headers, params={"days": 7}).json()["data"]
    assert usage["query_analytics"]["total_queries"] >= 1
    assert usage["document_analytics"]["total_documents"] >= 2
    assert usage["document_analytics"]["library_documents"] >= 2
    assert any(t["type"] == "Termination" for t in usage["top_query_types"])

    performance = client.get("/analytics/performance", headers=admin_headers).json()["data"]
    assert performance["performance_distribution"]

    similarity = client.get("/analytics/similarity", headers=admin_headers).json()["data"]
    assert similarity["overall_stats"]["total_comparisons"] >= 1
    pair = similarity["similar_document_pairs"][0]
    assert -1.0 <= pair["similarity"] <= 1.0

    specific = client.get("/analytics/similarity", headers=admin_headers,
                          params={"document_id": msa_id}).json()["data"]
    assert any(d["document_id"] == nda_id for d in specific["similar_documents"])

    activity = client.get("/analytics/activity", headers=admin_headers).json()["data"]
    assert activity["active_users"] >= 1
    assert any(a["type"] == "query.ask" for a in activity["activity_types"])

    report = client.get("/analytics/report", headers=admin_headers).json()
    assert report["audit_integrity"]["valid"] is True

    for doc_id in (msa_id, nda_id):
        client.delete(f"/documents/{doc_id}", headers=admin_headers)
