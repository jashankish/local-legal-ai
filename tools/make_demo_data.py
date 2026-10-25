#!/usr/bin/env python3
"""Generate the fixture data the static web demo (web/) ships with.

The public demo at yappertech.com/legal-ai-demo runs entirely in the visitor's
browser: there is no API, no ChromaDB and no model behind it. So the library it
searches has to be baked in. This script builds that library from the real
sample agreements in samples/, using the product's OWN clause-aware chunker
(rag.embedder.LegalDocumentEmbedder) and its own entity extractor
(rag.legal_insights), so the passages a visitor is shown are exactly the
passages the real pipeline would index and cite.

The output is committed to web/demo/, which keeps the site build free of Python
dependencies. CI regenerates it and fails if it differs from what is committed,
so the demo can never drift away from the product.

    .venv/bin/python tools/make_demo_data.py          # write web/demo/*.json
    .venv/bin/python tools/make_demo_data.py --check  # verify, write nothing
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Importing the real chunker pulls in backend.config, which requires a secret key.
# Nothing here signs anything; this only satisfies the settings validation.
os.environ.setdefault("SECRET_KEY", "demo-data-generator-not-a-real-secret-key-0123456789")

from rag.embedder import LegalDocumentEmbedder  # noqa: E402
from rag.legal_insights import extract_legal_entities  # noqa: E402

OUT_DIR = os.path.join(ROOT, "web", "demo")

# The library the demo ships with: the same fictional agreements scripts/seed_demo.py
# loads into a real instance, so the demo and a seeded local install look alike.
# (path, filename shown in the UI, title, category, document_type, uploaded_by, day offset)
LIBRARY = [
    ("samples/master_services_agreement.txt", "master_services_agreement.txt",
     "Master Services Agreement — Harborview / Meridian", "contracts", "contract", "admin", 6),
    ("samples/sources/mutual_nda.txt", "mutual_nda.docx",
     "Mutual NDA — Cobalt Ridge / Lindenfield", "nda", "nda", "admin", 6),
    ("samples/sources/commercial_lease.txt", "commercial_lease.pdf",
     "Commercial Lease — 410 Market Street", "real_estate", "lease", "admin", 6),
    ("samples/employment_agreement.txt", "employment_agreement.txt",
     "Employment Agreement — Senior Corporate Counsel", "employment", "employment", "admin", 5),
    ("samples/inbox/software_license_agreement.txt", "software_license_agreement.txt",
     "Software License Agreement — Quillmark / Alder & Finch", "contracts", "license", "inbox", 3),
    ("samples/sources/lease_amendment.txt", "scanned_lease_amendment.pdf",
     "First Amendment to Commercial Lease — 410 Market Street", "real_estate", "lease", "inbox", 1),
]

# Documents that reach the library through the watched inbox folder rather than an upload.
VIA_INBOX = {"software_license_agreement.txt", "scanned_lease_amendment.pdf"}

# Questions the demo's analytics, audit trail and "recent questions" are built from.
# They are the questions scripts/seed_demo.py asks, so the numbers are plausible.
SEEDED_QUESTIONS = [
    ("admin", "What notice period is required to terminate the services agreement for convenience?", 0.84, 0.31),
    ("admin", "What is the monthly retainer and when is it invoiced?", 0.81, 0.27),
    ("admin", "How long do the NDA confidentiality obligations survive?", 0.79, 0.24),
    ("j.ellis", "What is the base rent for the Market Street lease and how does it escalate?", 0.88, 0.29),
    ("j.ellis", "Can the tenant terminate the lease early?", 0.82, 0.37),
    ("j.ellis", "What severance is owed if the employee is terminated without cause?", 0.86, 0.22),
    ("j.ellis", "Which state's law governs the services agreement and how are disputes resolved?", 0.74, 0.41),
    ("j.ellis", "Summarize the limitation of liability clause.", 0.71, 0.52),
    ("m.okafor", "What are the payment terms and late-payment consequences?", 0.77, 0.33),
    ("m.okafor", "Who is responsible for maintenance and repairs?", 0.69, 0.28),
]

# A fixed clock so regenerating the fixtures produces identical bytes (CI --check).
NOW = datetime(2026, 10, 20, 16, 40, 0, tzinfo=timezone.utc)

MIME = {".txt": "text/plain", ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}


def stable_id(*parts: str) -> str:
    """A deterministic stand-in for the uuid a real upload would get."""
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]


def section_title(text: str) -> str:
    """The clause heading a passage sits under, for display next to a citation."""
    match = re.match(r"\s*(Section|Article)\s+(\d+)\.\s*([A-Z][A-Za-z ,'&/-]{2,60}?)\.", text)
    if match:
        return f"{match.group(1)} {match.group(2)}. {match.group(3).strip()}"
    match = re.match(r"\s*(Section|Article)\s+(\d+)", text)
    if match:
        return f"{match.group(1)} {match.group(2)}"
    return ""


def build_library(embedder):
    """Chunk every sample document the way the real ingestion pipeline would."""
    documents, passages = [], []
    for path, filename, title, category, doc_type, uploaded_by, days_ago in LIBRARY:
        full_path = os.path.join(ROOT, path)
        with open(full_path, encoding="utf-8") as handle:
            text = handle.read()

        document_id = stable_id(filename, title)
        uploaded = NOW - timedelta(days=days_ago, hours=days_ago * 3 % 7, minutes=days_ago * 11 % 53)
        chunks = embedder.chunk_legal_document(text, {"source": title, "category": category})

        for index, chunk in enumerate(chunks):
            body = chunk["text"] if isinstance(chunk, dict) else str(chunk)
            body = body.strip()
            if not body:
                continue
            passages.append({
                "id": f"{document_id}-{index:04d}",
                "document_id": document_id,
                "chunk_index": index,
                "section": section_title(body),
                "text": body,
            })

        indexed = [p for p in passages if p["document_id"] == document_id]
        documents.append({
            "id": document_id,
            "filename": filename,
            "source": title,
            "category": category,
            "document_type": doc_type,
            "page_count": 1 if filename.endswith(".txt") else max(1, round(len(text.split()) / 420)),
            "word_count": len(text.split()),
            "char_count": len(text),
            "chunk_count": len(indexed),
            "uploaded_by": uploaded_by,
            "upload_date": uploaded.strftime("%Y-%m-%dT%H:%M:%S"),
            "content_type": MIME.get(os.path.splitext(filename)[1], "text/plain"),
            "file_size": len(text.encode()) + (28_000 if filename.endswith(".docx") else 0)
                         + (3_900 if filename.endswith(".pdf") else 0),
            "ocr": filename == "scanned_lease_amendment.pdf",
            "via_inbox": filename in VIA_INBOX,
        })
    return documents, passages


def build_analytics(documents, passages):
    """The numbers behind the five Analytics tabs, derived from the library itself."""
    total_queries = len(SEEDED_QUESTIONS)
    users = sorted({user for user, *_ in SEEDED_QUESTIONS})
    avg_similarity = sum(score for _, _, score, _ in SEEDED_QUESTIONS) / total_queries
    avg_time = sum(seconds for *_, seconds in SEEDED_QUESTIONS) / total_queries

    # Spread the questions over the last few days so the trend chart has a shape.
    spread = [3, 3, 2, 2, 2, 1, 1, 1, 0, 0]
    daily = {}
    for (_, _, _, _), offset in zip(SEEDED_QUESTIONS, spread):
        day = (NOW - timedelta(days=offset)).strftime("%Y-%m-%d")
        daily[day] = daily.get(day, 0) + 1
    uploads_by_day = {}
    for document in documents:
        day = document["upload_date"][:10]
        uploads_by_day[day] = uploads_by_day.get(day, 0) + 1

    daily_trends = [{"date": day, "queries": daily.get(day, 0), "documents": uploads_by_day.get(day, 0)}
                    for day in sorted(set(daily) | set(uploads_by_day))]

    def band(seconds):
        if seconds < 0.1:
            return "very_fast"
        if seconds < 0.5:
            return "fast"
        if seconds < 1:
            return "moderate"
        return "slow" if seconds < 2 else "very_slow"

    def quality(score):
        if score >= 0.85:
            return "excellent"
        if score >= 0.75:
            return "good"
        if score >= 0.6:
            return "fair"
        return "poor" if score >= 0.4 else "very_poor"

    performance_counts, quality_counts = {}, {}
    for _, _, score, seconds in SEEDED_QUESTIONS:
        performance_counts[band(seconds)] = performance_counts.get(band(seconds), 0) + 1
        quality_counts[quality(score)] = quality_counts.get(quality(score), 0) + 1

    slowest = sorted(SEEDED_QUESTIONS, key=lambda row: -row[3])[:5]

    # Which clause a question is about, for the query-type pie chart.
    types = {"Termination & notice": 0, "Fees & payment": 0, "Confidentiality": 0,
             "Liability & risk": 0, "Other": 0}
    for _, question, _, _ in SEEDED_QUESTIONS:
        lowered = question.lower()
        if any(word in lowered for word in ("terminate", "termination", "notice", "severance")):
            types["Termination & notice"] += 1
        elif any(word in lowered for word in ("retainer", "rent", "payment", "invoice", "fee")):
            types["Fees & payment"] += 1
        elif any(word in lowered for word in ("confidential", "nda", "disclos")):
            types["Confidentiality"] += 1
        elif any(word in lowered for word in ("liability", "indemn", "governs", "dispute")):
            types["Liability & risk"] += 1
        else:
            types["Other"] += 1

    library_chunks = len(passages)
    return {
        "usage": {
            "query_analytics": {
                "total_queries": total_queries,
                "unique_users": len(users),
                "avg_similarity_score": round(avg_similarity, 3),
                "avg_processing_time": round(avg_time, 3),
            },
            "document_analytics": {
                "total_documents": len(documents),
                "total_chunks": library_chunks,
                "avg_chunks_per_doc": round(library_chunks / len(documents), 1),
                "avg_file_size": round(sum(d["file_size"] for d in documents) / len(documents)),
                "avg_processing_time": 0.05,
                "library_documents": len(documents),
                "library_chunks": library_chunks,
            },
            "daily_trends": daily_trends,
            "top_query_types": [{"type": name, "count": count}
                                for name, count in types.items() if count],
        },
        "performance": {
            "performance_distribution": [
                {"category": name, "count": count,
                 "avg_time": round(sum(s for *_, s in SEEDED_QUESTIONS if band(s) == name) / count, 3)}
                for name, count in performance_counts.items()],
            "quality_distribution": [{"category": name, "count": count}
                                     for name, count in quality_counts.items()],
            "slowest_queries": [{"query": question, "processing_time": seconds, "similarity_score": score}
                                for _, question, score, seconds in slowest],
            "optimization_suggestions": [
                "Retrieval quality is good (average similarity 0.79). No tuning needed yet.",
                "Every question was answered in under a second — the index is comfortably sized.",
                "Connect a local model for generated answers; retrieval already returns the right clauses.",
            ],
        },
        "activity": {
            "active_users": len(users),
            "activity_types": [
                {"type": "query.ask", "count": total_queries},
                {"type": "auth.login", "count": 7},
                {"type": "document.upload", "count": len(documents)},
                {"type": "user.create", "count": 2},
                {"type": "analytics.export", "count": 1},
                {"type": "audit.verify", "count": 2},
            ],
            "hourly_patterns": [{"hour": f"{hour:02d}:00", "activity_count": count} for hour, count in
                                [(8, 2), (9, 5), (10, 7), (11, 4), (12, 1), (13, 2),
                                 (14, 6), (15, 5), (16, 3), (17, 1)]],
            "top_users": [{"user_id": user,
                           "activity_count": sum(1 for u, *_ in SEEDED_QUESTIONS if u == user) + 2}
                          for user in sorted(users, key=lambda u: -sum(1 for x, *_ in SEEDED_QUESTIONS if x == u))],
        },
        "similarity": build_similarity(documents),
    }


def build_similarity(documents):
    """Document-level similarity, highest between the lease and its amendment."""
    # Hand-set so the demo shows the realistic case: an amendment that closely
    # tracks the agreement it amends, and two commercial contracts that share
    # boilerplate (liability caps, renewal, governing law).
    scores = {
        ("commercial_lease.pdf", "scanned_lease_amendment.pdf"): 0.91,
        ("master_services_agreement.txt", "software_license_agreement.txt"): 0.83,
        ("master_services_agreement.txt", "employment_agreement.txt"): 0.64,
        ("mutual_nda.docx", "master_services_agreement.txt"): 0.61,
        ("employment_agreement.txt", "software_license_agreement.txt"): 0.55,
        ("mutual_nda.docx", "employment_agreement.txt"): 0.52,
        ("commercial_lease.pdf", "master_services_agreement.txt"): 0.49,
        ("mutual_nda.docx", "commercial_lease.pdf"): 0.44,
        ("commercial_lease.pdf", "software_license_agreement.txt"): 0.43,
        ("mutual_nda.docx", "software_license_agreement.txt"): 0.41,
        ("employment_agreement.txt", "scanned_lease_amendment.pdf"): 0.38,
        ("master_services_agreement.txt", "scanned_lease_amendment.pdf"): 0.37,
        ("mutual_nda.docx", "scanned_lease_amendment.pdf"): 0.33,
        ("software_license_agreement.txt", "scanned_lease_amendment.pdf"): 0.32,
        ("commercial_lease.pdf", "employment_agreement.txt"): 0.31,
    }
    by_name = {d["filename"]: d for d in documents}
    pairs = []
    for (first, second), similarity in scores.items():
        if first in by_name and second in by_name:
            pairs.append({"doc1": first, "doc2": second, "similarity": similarity,
                          "doc1_id": by_name[first]["id"], "doc2_id": by_name[second]["id"]})
    pairs.sort(key=lambda row: -row["similarity"])
    values = [row["similarity"] for row in pairs]
    return {
        "overall_stats": {
            "avg_similarity": round(sum(values) / len(values), 3),
            "max_similarity": max(values),
            "total_comparisons": len(values),
            "documents_compared": len(documents),
        },
        "similar_document_pairs": pairs,
    }


def build_audit(documents):
    """A hash-chained audit trail over the events the seeded library implies."""
    events = []

    def add(action, status, username, resource="", details=None, minutes_ago=0, ip="10.0.14.22"):
        events.append({
            "action": action, "status": status, "username": username, "resource": resource,
            "details": details or {}, "ip_address": ip,
            "timestamp": (NOW - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%S"),
        })

    add("auth.login", "success", "admin", minutes_ago=9_300)
    add("auth.password_change", "success", "admin", minutes_ago=9_295)
    for document in sorted(documents, key=lambda d: d["upload_date"]):
        minutes = int((NOW - datetime.fromisoformat(document["upload_date"]).replace(
            tzinfo=timezone.utc)).total_seconds() // 60)
        add("document.upload", "success", document["uploaded_by"], document["filename"],
            {"passages": document["chunk_count"], "category": document["category"],
             **({"ocr": True} if document["ocr"] else {}),
             **({"via": "inbox"} if document["via_inbox"] else {})},
            minutes_ago=minutes, ip="127.0.0.1" if document["via_inbox"] else "10.0.14.22")
    add("user.create", "success", "admin", "j.ellis", {"role": "lawyer"}, minutes_ago=8_900)
    add("user.create", "success", "admin", "m.okafor", {"role": "lawyer"}, minutes_ago=8_880)
    add("auth.login", "failure", "j.ellis", details={"reason": "bad password"}, minutes_ago=8_500,
        ip="10.0.14.51")
    add("auth.login", "success", "j.ellis", minutes_ago=8_495, ip="10.0.14.51")
    add("auth.password_change", "success", "j.ellis", minutes_ago=8_493, ip="10.0.14.51")
    for index, (user, question, score, seconds) in enumerate(SEEDED_QUESTIONS):
        add("query.ask", "success", user, details={
            "passages": 5, "top_similarity": score, "seconds": seconds,
            "question": question[:80]}, minutes_ago=4_200 - index * 37,
            ip={"admin": "10.0.14.22", "j.ellis": "10.0.14.51", "m.okafor": "10.0.14.63"}[user])
    add("access.ip_denied", "denied", "", details={"reason": "outside IP allow-list"},
        minutes_ago=3_100, ip="203.0.113.9")
    add("analytics.export", "success", "admin", "analytics_report.json", minutes_ago=2_400)
    add("audit.verify", "success", "admin", details={"checked": 0}, minutes_ago=1_800)
    add("document.delete", "success", "admin", "draft_nda_v1.txt", {"passages": 6}, minutes_ago=900)
    add("integration.test", "success", "admin", "n8n", {"status_code": 200}, minutes_ago=240)
    add("auth.login", "success", "m.okafor", minutes_ago=180, ip="10.0.14.63")

    events.sort(key=lambda event: event["timestamp"])

    # Hash chain: each entry seals the previous hash, exactly like security/audit_log.py.
    previous = "0" * 64
    for index, event in enumerate(events, start=1):
        event["id"] = index
        payload = json.dumps({k: event[k] for k in
                              ("id", "timestamp", "action", "status", "username", "resource", "details")},
                             sort_keys=True, separators=(",", ":"))
        event["previous_hash"] = previous
        event["hash"] = hashlib.sha256((previous + payload).encode()).hexdigest()
        previous = event["hash"]

    for event in events:
        if event["action"] == "audit.verify":
            event["details"] = {"checked": len(events)}

    by_action, by_status = {}, {}
    for event in events:
        by_action[event["action"]] = by_action.get(event["action"], 0) + 1
        by_status[event["status"]] = by_status.get(event["status"], 0) + 1
    return {"events": list(reversed(events)), "total": len(events),
            "summary": {"by_action": by_action, "by_status": by_status}}


def build_users():
    def when(days, hour):
        return (NOW - timedelta(days=days)).replace(hour=hour, minute=12).strftime("%Y-%m-%dT%H:%M:%S")

    return {"users": [
        {"username": "admin", "email": "admin@fernwoodlegal.example", "role": "admin",
         "is_active": True, "must_change_password": False,
         "last_login": when(0, 9), "created_at": when(21, 8)},
        {"username": "j.ellis", "email": "j.ellis@fernwoodlegal.example", "role": "lawyer",
         "is_active": True, "must_change_password": False,
         "last_login": when(1, 14), "created_at": when(18, 11)},
        {"username": "m.okafor", "email": "m.okafor@fernwoodlegal.example", "role": "lawyer",
         "is_active": True, "must_change_password": False,
         "last_login": when(0, 11), "created_at": when(18, 11)},
        {"username": "r.santos", "email": "r.santos@fernwoodlegal.example", "role": "user",
         "is_active": True, "must_change_password": True,
         "last_login": None, "created_at": when(2, 16)},
        {"username": "p.greaves", "email": "", "role": "user",
         "is_active": False, "must_change_password": False,
         "last_login": when(40, 10), "created_at": when(60, 9)},
    ]}


def build_integrations(documents):
    inbox_documents = [d for d in documents if d["via_inbox"]]
    recent = [{
        "timestamp": d["upload_date"],
        "file": d["filename"],
        "category": d["category"],
        "ok": True,
        "passages": d["chunk_count"],
        "moved_to": f"data/inbox/_processed/{d['filename']}",
    } for d in sorted(inbox_documents, key=lambda d: d["upload_date"], reverse=True)]
    recent.append({
        "timestamp": (NOW - timedelta(hours=20)).strftime("%Y-%m-%dT%H:%M:%S"),
        "file": "corrupt_scan.pdf", "category": "general", "ok": False,
        "error": "no extractable text (and OCR found none)", "moved_to": "data/inbox/_failed/corrupt_scan.pdf",
    })
    return {
        "inbox": {
            "running": True,
            "inbox_dir": "data/inbox",
            "interval_seconds": 15,
            "processed": len(inbox_documents),
            "failed": 1,
            "waiting": 0,
            "last_scan": (NOW - timedelta(seconds=9)).strftime("%Y-%m-%dT%H:%M:%S"),
            "recent": recent,
        },
        "notifications": {
            "enabled": True,
            "n8n": {"configured": True, "target": "http://n8n.internal:5678/webhook/legal-ai", "signed": True},
            "slack": {"configured": True, "target": "#legal-ops"},
            "events": ["document.upload", "document.delete", "user.create",
                       "auth.login_failed", "access.ip_denied"],
            "recent_deliveries": [
                {"timestamp": (NOW - timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%S"),
                 "event": "integration.test", "target": "n8n", "ok": True, "attempts": 1},
                {"timestamp": (NOW - timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%S"),
                 "event": "integration.test", "target": "slack", "ok": True, "attempts": 1},
                {"timestamp": (NOW - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S"),
                 "event": "document.upload", "target": "n8n", "ok": True, "attempts": 1},
                {"timestamp": (NOW - timedelta(days=1, minutes=3)).strftime("%Y-%m-%dT%H:%M:%S"),
                 "event": "document.upload", "target": "slack", "ok": False,
                 "error": "HTTP 429 rate limited", "attempts": 3},
            ],
        },
    }


def build_entities(passages):
    """Pre-extract key terms per passage with the product's own extractor."""
    return {passage["id"]: extract_legal_entities(passage["text"]) for passage in passages}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="fail if the committed files differ from freshly generated ones")
    args = parser.parse_args()

    embedder = LegalDocumentEmbedder.__new__(LegalDocumentEmbedder)
    embedder.chunk_size = 512
    embedder.chunk_overlap = 50
    embedder.section_patterns = [
        r'\n\s*(?:Section|Article|Chapter|Part)\s+\d+',
        r'\n\s*\d+\.\s+',
        r'\n\s*\([a-z]\)\s+',
        r'\n\s*[A-Z][A-Z\s]{10,}\n',
    ]

    documents, passages = build_library(embedder)
    files = {
        "library.json": {
            "documents": documents,
            "passages": passages,
            "stats": {"document_count": len(documents), "chunk_count": len(passages),
                      "name": "legal_documents", "status": "healthy"},
        },
        "entities.json": build_entities(passages),
        "analytics.json": build_analytics(documents, passages),
        "audit.json": build_audit(documents),
        "users.json": build_users(),
        "integrations.json": build_integrations(documents),
        "questions.json": {"seeded": [{"user": user, "question": question,
                                       "similarity": score, "seconds": seconds}
                                      for user, question, score, seconds in SEEDED_QUESTIONS]},
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    stale = []
    for name, payload in files.items():
        rendered = json.dumps(payload, indent=1, sort_keys=False) + "\n"
        path = os.path.join(OUT_DIR, name)
        if args.check:
            existing = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
            if existing != rendered:
                stale.append(name)
            continue
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(rendered)
        print(f"  {name}: {len(rendered):,} bytes")

    if args.check:
        if stale:
            sys.exit("web/demo is out of date (" + ", ".join(stale) +
                     "). Run: python tools/make_demo_data.py")
        print("web/demo matches the samples and the product's chunker.")
        return
    print(f"Wrote {len(files)} files to web/demo/ "
          f"({len(documents)} documents, {len(passages)} passages).")


if __name__ == "__main__":
    main()
