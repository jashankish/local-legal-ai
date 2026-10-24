"""Document registry: it must always agree with the vector store."""

from tests.test_api import upload


def chroma_document_ids():
    """Group chunk metadata exactly as the pre-registry code did, for comparison."""
    from backend.app import chroma_manager
    from backend import registry

    results = chroma_manager.collection.get(include=["metadatas"])
    return registry.group_chunk_metadata(results.get("ids", []), results.get("metadatas", []))


def test_registry_matches_the_vector_store_after_upload_and_delete(client, admin_headers):
    from backend import registry

    body = upload(client, admin_headers, name="registry-msa.txt").json()
    document_id = body["document_id"]

    record = registry.get(document_id)
    assert record is not None
    assert record["chunk_count"] == body["chunks_processed"]
    assert record["filename"] == "registry-msa.txt"
    assert record["category"] == "contracts"
    assert record["uploaded_by"] == "admin"
    assert record["document_type"], "the detected legal document type is recorded"
    assert chroma_document_ids()[document_id]["chunk_count"] == record["chunk_count"]

    listed = client.get("/documents", headers=admin_headers).json()
    entry = next(d for d in listed["documents"] if d["id"] == document_id)
    assert entry["chunk_count"] == record["chunk_count"]
    assert "chunk_ids" not in entry, "chunk ids are resolved on demand, not listed"

    client.delete(f"/documents/{document_id}", headers=admin_headers)
    assert registry.get(document_id) is None
    assert document_id not in chroma_document_ids()


def test_stats_counts_documents_not_chunks(client, admin_headers):
    first = upload(client, admin_headers, name="registry-stats-1.txt").json()
    second = upload(client, admin_headers, name="registry-stats-2.txt").json()

    stats = client.get("/documents/stats", headers=admin_headers).json()
    assert stats["document_count"] >= 2
    assert stats["chunk_count"] >= stats["document_count"]

    for document_id in (first["document_id"], second["document_id"]):
        client.delete(f"/documents/{document_id}", headers=admin_headers)


def test_reconcile_adopts_legacy_chunks_that_predate_document_id(client, admin_headers):
    """Documents indexed before document_id existed are grouped by their source name."""
    from backend.app import chroma_manager
    from backend import registry

    ids = ["legacy-chunk-0", "legacy-chunk-1"]
    chroma_manager.collection.add(
        ids=ids,
        documents=["Section 1. The tenant shall pay rent monthly.",
                   "Section 2. The agreement is governed by the laws of Texas."],
        metadatas=[{"source": "Legacy Lease", "category": "real_estate",
                    "uploaded_by": "archivist"} for _ in ids],
    )
    try:
        result = registry.reconcile(chroma_manager.collection)
        assert result["added"] >= 1

        record = registry.get("Legacy Lease")
        assert record is not None, "grouped by source when document_id is absent"
        assert record["chunk_count"] == 2
        assert record["uploaded_by"] == "archivist"
        # Deletion must still find the chunks, via the source fallback.
        assert sorted(registry.chunk_ids(chroma_manager.collection, "Legacy Lease")) == ids

        listed = client.get("/documents", headers=admin_headers).json()["documents"]
        assert any(d["id"] == "Legacy Lease" for d in listed)
    finally:
        chroma_manager.collection.delete(ids=ids)
        registry.reconcile(chroma_manager.collection)

    assert registry.get("Legacy Lease") is None, "reconcile drops documents whose chunks are gone"


def test_reconcile_is_idempotent_and_repairs_drift(client, admin_headers):
    from backend.app import chroma_manager
    from backend import registry, store

    body = upload(client, admin_headers, name="registry-drift.txt").json()
    document_id = body["document_id"]

    first = registry.reconcile(chroma_manager.collection)
    assert first == {"added": 0, "updated": 0, "removed": 0}, "a settled registry needs no changes"

    # Simulate a stale count, then prove reconcile repairs it.
    store.execute("UPDATE documents SET chunk_count = 999 WHERE document_id = ?", (document_id,))
    repaired = registry.reconcile(chroma_manager.collection)
    assert repaired["updated"] == 1
    assert registry.get(document_id)["chunk_count"] == body["chunks_processed"]

    client.delete(f"/documents/{document_id}", headers=admin_headers)
