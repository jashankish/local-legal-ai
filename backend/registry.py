"""Document registry: one row per uploaded document.

Document identity used to be derived by scanning every chunk's metadata in the
vector store on each call. That is linear in the size of the whole library and
happens on listing, stats, deletion and analytics. This module keeps the same
facts in `data/app.db` so those reads are indexed lookups, and gives
document-level attributes (matter, retention) somewhere to live.

The vector store stays the source of truth for passages; `reconcile()` rebuilds
the registry from it, so the registry can always be thrown away and recreated.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from backend import store

logger = logging.getLogger(__name__)

# Columns selected into the document record the API returns.
_FIELDS = ("filename", "source", "category", "document_type", "uploaded_by", "upload_date",
           "content_type", "file_size", "page_count", "word_count", "chunk_count",
           "ingest_channel", "matter_id", "lookup_field")


def _record_from_metadata(doc_id: str, metadata: Dict[str, Any], chunk_count: int,
                          lookup_field: str) -> Dict[str, Any]:
    """Normalise chunk metadata into a registry row, matching the long-standing API defaults."""
    return {
        "document_id": doc_id,
        "filename": metadata.get("filename") or metadata.get("source", "Unknown"),
        "source": metadata.get("source", "Unknown"),
        "category": metadata.get("category", "general"),
        "document_type": (metadata.get("legal_document_type")
                          or metadata.get("document_type", "general")),
        "uploaded_by": metadata.get("uploaded_by", "Unknown"),
        "upload_date": metadata.get("upload_date", "Unknown"),
        "content_type": metadata.get("content_type", "text/plain"),
        "file_size": metadata.get("file_size", 0),
        "page_count": metadata.get("page_count"),
        "word_count": metadata.get("word_count"),
        "chunk_count": chunk_count,
        "ingest_channel": metadata.get("ingest_channel"),
        "matter_id": metadata.get("matter_id"),
        "lookup_field": lookup_field,
    }


def _to_api(row: Dict[str, Any]) -> Dict[str, Any]:
    """The shape callers have always received, keyed by `id`."""
    record = {"id": row["document_id"]}
    record.update({field: row.get(field) for field in _FIELDS if field != "lookup_field"})
    return record


def upsert(doc_id: str, metadata: Dict[str, Any], chunk_count: int,
           lookup_field: str = "document_id") -> Dict[str, Any]:
    """Insert or replace one document's registry row."""
    record = _record_from_metadata(doc_id, metadata, chunk_count, lookup_field)
    columns = ["document_id", *_FIELDS, "created_at"]
    values = [record["document_id"], *[record[f] for f in _FIELDS],
              datetime.utcnow().isoformat()]
    placeholders = ", ".join("?" * len(columns))
    store.execute(
        f"INSERT INTO documents ({', '.join(columns)}) VALUES ({placeholders}) "
        f"ON CONFLICT(document_id) DO UPDATE SET "
        + ", ".join(f"{field}=excluded.{field}" for field in _FIELDS),
        values,
    )
    return _to_api(record)


def remove(doc_id: str) -> None:
    store.execute("DELETE FROM documents WHERE document_id = ?", (doc_id,))


def get(doc_id: str) -> Optional[Dict[str, Any]]:
    row = store.query_one("SELECT * FROM documents WHERE document_id = ?", (doc_id,))
    return _to_api(row) if row else None


def lookup_filter(doc_id: str) -> Optional[Dict[str, str]]:
    """The vector-store `where` clause that selects this document's chunks."""
    row = store.query_one("SELECT document_id, lookup_field, source FROM documents "
                          "WHERE document_id = ?", (doc_id,))
    if row is None:
        return None
    if row["lookup_field"] == "source":
        return {"source": row["source"]}
    return {"document_id": row["document_id"]}


def all_documents() -> List[Dict[str, Any]]:
    """Every document, newest upload first."""
    rows = store.query("SELECT * FROM documents ORDER BY upload_date DESC, document_id")
    return [_to_api(row) for row in rows]


def as_grouped() -> Dict[str, Dict[str, Any]]:
    """Registry contents keyed by document id (the historical `_group_chunks_by_document` shape)."""
    return {record["id"]: record for record in all_documents()}


def totals() -> Dict[str, int]:
    row = store.query_one("SELECT COUNT(*) AS documents, "
                          "COALESCE(SUM(chunk_count), 0) AS chunks FROM documents")
    return {"documents": row["documents"], "chunks": row["chunks"]} if row else {"documents": 0, "chunks": 0}


def chunk_ids(collection, doc_id: str) -> List[str]:
    """Resolve a document's chunk ids from the vector store (authoritative for deletion)."""
    where = lookup_filter(doc_id)
    if where is None:
        return []
    try:
        return list(collection.get(where=where, include=[]).get("ids", []))
    except Exception as e:
        logger.error(f"Could not resolve chunk ids for {doc_id}: {e}")
        return []


def group_chunk_metadata(ids: Iterable[str], metadatas: Iterable[Optional[Dict[str, Any]]]
                         ) -> Dict[str, Dict[str, Any]]:
    """Collapse raw chunk metadata into per-document rows (used by reconcile)."""
    grouped: Dict[str, Dict[str, Any]] = {}
    for chunk_id, metadata in zip(ids, metadatas):
        metadata = metadata or {}
        # Chunks stored before document_id existed are grouped by their source name.
        doc_id = metadata.get("document_id") or metadata.get("source") or chunk_id
        lookup_field = "document_id" if metadata.get("document_id") else "source"
        entry = grouped.setdefault(doc_id, {
            "metadata": metadata, "chunk_count": 0, "lookup_field": lookup_field,
        })
        entry["chunk_count"] += 1
    return grouped


def reconcile(collection) -> Dict[str, int]:
    """Rebuild the registry from the vector store.

    Adds documents that are missing, refreshes chunk counts that drifted and drops
    rows whose chunks are gone. Idempotent, so it is safe to run on every start.
    """
    try:
        results = collection.get(include=["metadatas"])
    except Exception as e:
        logger.error(f"Registry reconcile skipped, could not read the vector store: {e}")
        return {"added": 0, "updated": 0, "removed": 0}

    grouped = group_chunk_metadata(results.get("ids", []), results.get("metadatas", []))
    existing = {row["document_id"]: row for row in store.query("SELECT * FROM documents")}
    added = updated = 0

    for doc_id, entry in grouped.items():
        current = existing.get(doc_id)
        if current is None:
            upsert(doc_id, entry["metadata"], entry["chunk_count"], entry["lookup_field"])
            added += 1
        elif current["chunk_count"] != entry["chunk_count"]:
            store.execute("UPDATE documents SET chunk_count = ? WHERE document_id = ?",
                          (entry["chunk_count"], doc_id))
            updated += 1

    orphaned = [doc_id for doc_id in existing if doc_id not in grouped]
    for doc_id in orphaned:
        remove(doc_id)

    if added or updated or orphaned:
        logger.info(f"Document registry reconciled: +{added} added, {updated} updated, "
                    f"{len(orphaned)} removed")
    return {"added": added, "updated": updated, "removed": len(orphaned)}
