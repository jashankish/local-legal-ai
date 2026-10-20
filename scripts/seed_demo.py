"""Load the sample library into a running instance and generate realistic activity.

Usage: .venv/bin/python scripts/seed_demo.py [--backend http://127.0.0.1:8000]

Signs in as admin (completing the first-login password change if needed),
uploads every file in samples/, creates a small demo team and asks a set of
typical questions so the analytics dashboard, audit log and user pages have
data to show. Run it against a fresh instance; it does not delete anything.
"""

import argparse
import os
import sys
import time

import requests

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SAMPLES = [
    ("master_services_agreement.txt", "Master Services Agreement — Harborview / Meridian", "contracts"),
    ("mutual_nda.docx", "Mutual NDA — Cobalt Ridge / Lindenfield", "nda"),
    ("commercial_lease.pdf", "Commercial Lease — 410 Market Street", "real_estate"),
    ("employment_agreement.txt", "Employment Agreement — Senior Corporate Counsel", "employment"),
]
QUESTIONS = {
    "admin": [
        "What notice period is required to terminate the services agreement for convenience?",
        "What is the monthly retainer and when is it invoiced?",
        "How long do the NDA confidentiality obligations survive?",
    ],
    "associate": [
        "What is the base rent for the Market Street lease and how does it escalate?",
        "Can the tenant terminate the lease early?",
        "What severance is owed if the employee is terminated without cause?",
        "Which state's law governs the services agreement and how are disputes resolved?",
        "Summarize the limitation of liability clause.",
    ],
}
MIME = {".txt": "text/plain", ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}


def login(base, username, password):
    response = requests.post(f"{base}/auth/login", json={"username": username, "password": password}, timeout=30)
    response.raise_for_status()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def admin_session(base, new_password):
    """Sign in as admin; replace the default password on a fresh install."""
    for password in (new_password, "admin123"):
        response = requests.post(f"{base}/auth/login", timeout=30,
                                 json={"username": "admin", "password": password})
        if response.status_code != 200:
            continue
        body = response.json()
        token = body["access_token"]
        if body["user"].get("must_change_password"):
            changed = requests.post(f"{base}/auth/change-password", timeout=30,
                                    headers={"Authorization": f"Bearer {token}"},
                                    json={"current_password": password, "new_password": new_password})
            changed.raise_for_status()
            token = changed.json()["access_token"]
            print(f"admin password set to: {new_password}")
        return {"Authorization": f"Bearer {token}"}
    sys.exit("Could not sign in as admin with the default or the provided password")


TEAM = [
    # username, password, role, must change at first sign-in, active
    ("associate", "associate-demo-1", "lawyer", False, True),
    ("paralegal", "paralegal-demo-1", "user", False, True),
    ("new.hire", "Welcome-temp-1", "lawyer", True, True),
    ("former.counsel", "former-demo-1", "lawyer", False, False),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default=os.getenv("BACKEND_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--admin-password", default=os.getenv("ADMIN_PASSWORD", "LegalDemo-2025"),
                        help="Password to set for admin on a fresh install (or the current one)")
    args = parser.parse_args()
    base = args.backend.rstrip("/")

    for _ in range(60):
        try:
            if requests.get(f"{base}/health", timeout=2).ok:
                break
        except requests.RequestException:
            pass
        time.sleep(1)
    else:
        sys.exit(f"Backend not reachable at {base}")

    admin = admin_session(base, args.admin_password)
    for filename, title, category in SAMPLES:
        path = os.path.join(ROOT, "samples", filename)
        with open(path, "rb") as f:
            response = requests.post(
                f"{base}/documents/upload", headers=admin, timeout=300,
                files={"file": (filename, f, MIME[os.path.splitext(filename)[1]])},
                data={"title": title, "category": category},
            ).json()
        print(f"uploaded {filename}: {response.get('chunks_processed')} passages ({response.get('message')})")

    for username, password, role, must_change, active in TEAM:
        requests.post(f"{base}/auth/register", headers=admin, timeout=30, json={
            "username": username, "password": password, "email": f"{username}@firm.local",
            "role": role, "must_change_password": must_change,
        })
        if not active:
            requests.patch(f"{base}/users/{username}", headers=admin, timeout=30, json={"is_active": False})
        print(f"user {username} ({role}{', must change password' if must_change else ''}"
              f"{', disabled' if not active else ''})")
    users = {"admin": admin, "associate": login(base, "associate", "associate-demo-1")}
    login(base, "paralegal", "paralegal-demo-1")

    # One failed sign-in so the audit log shows a denied event.
    requests.post(f"{base}/auth/login", json={"username": "associate", "password": "wrong-password"}, timeout=30)

    for username, questions in QUESTIONS.items():
        for question in questions:
            answer = requests.post(f"{base}/query", headers=users[username], timeout=300,
                                   json={"question": question, "num_documents": 4}).json()
            print(f"[{username}] {question} -> {answer.get('mode')} ({answer.get('confidence_score')})")
    print("Demo data loaded.")


if __name__ == "__main__":
    main()
