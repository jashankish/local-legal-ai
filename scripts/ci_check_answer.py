"""Post-deployment check against a running, seeded instance (used by CI).

Examples:
  python scripts/ci_check_answer.py --expect-mode extractive
  python scripts/ci_check_answer.py --expect-mode generative --wait 900
  python scripts/ci_check_answer.py --expect-document software_license_agreement.txt --wait 90

Exits non-zero if the expectation isn't met within --wait seconds.
"""

import argparse
import os
import sys
import time

import requests

QUESTION = "Can the tenant terminate the lease early, and what does it cost?"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default=os.getenv("BACKEND_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--password", default=os.getenv("ADMIN_PASSWORD", "LegalDemo-2025"))
    parser.add_argument("--expect-mode", choices=["extractive", "generative"])
    parser.add_argument("--expect-document")
    parser.add_argument("--wait", type=int, default=0, help="seconds to keep retrying")
    args = parser.parse_args()
    base = args.backend.rstrip("/")

    token = requests.post(f"{base}/auth/login", timeout=30,
                          json={"username": "admin", "password": args.password}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    deadline = time.time() + args.wait
    last = None

    while True:
        if args.expect_document:
            documents = requests.get(f"{base}/documents", headers=headers, timeout=30).json()["documents"]
            match = next((d for d in documents if d["filename"] == args.expect_document), None)
            if match:
                print(f"OK: {match['filename']} indexed ({match['chunk_count']} passages, "
                      f"category {match['category']}, uploaded by {match['uploaded_by']})")
                return 0
            last = f"{args.expect_document} not in library ({len(documents)} documents)"
        else:
            result = requests.post(f"{base}/query", headers=headers, timeout=300,
                                   json={"question": QUESTION, "num_documents": 4}).json()
            if result.get("mode") == args.expect_mode and result.get("sources"):
                print(f"OK: {result['mode']} answer (model {result.get('model')}, "
                      f"citations {result.get('citations')}, {result.get('processing_time', 0):.2f}s)")
                print(result["answer"])
                return 0
            last = f"mode={result.get('mode')} answer={str(result.get('answer'))[:200]!r}"

        if time.time() >= deadline:
            print(f"FAILED: {last}", file=sys.stderr)
            return 1
        time.sleep(10)


if __name__ == "__main__":
    sys.exit(main())
