"""Render every Streamlit page as admin against a live backend and report exceptions.

Usage: BACKEND_URL=http://127.0.0.1:8000 ADMIN_PASSWORD=... .venv/bin/python scripts/ui_smoke.py "$PWD/frontend/streamlit_app.py"
"""
import os
import sys
import time

import requests
from streamlit.testing.v1 import AppTest

BACKEND = os.environ["BACKEND_URL"]
APP = sys.argv[1]

for _ in range(60):
    try:
        if requests.get(f"{BACKEND}/health", timeout=2).ok:
            break
    except Exception:
        pass
    time.sleep(1)

login = requests.post(f"{BACKEND}/auth/login", json={
    "username": "admin", "password": os.environ.get("ADMIN_PASSWORD", "admin123")}).json()
if "access_token" not in login:
    sys.exit(f"Admin sign-in failed ({login}); set ADMIN_PASSWORD")
if login["user"].get("must_change_password"):
    sys.exit("Admin still has the default password; change it (or run scripts/seed_demo.py) first")

at = AppTest.from_file(APP, default_timeout=60)
at.session_state["authenticated"] = True
at.session_state["access_token"] = login["access_token"]
at.session_state["user_info"] = login["user"]
at.run()

nav = at.sidebar.selectbox(key="main_navigation")
failures = 0
for page in nav.options:
    at.sidebar.selectbox(key="main_navigation").set_value(page).run()
    problems = [e.value for e in at.exception]
    errors = [e.value for e in at.error]
    status = "OK" if not problems else "EXCEPTION"
    failures += bool(problems)
    print(f"{status:9} {page}  errors={errors[:2]}  exceptions={[p[:200] for p in problems][:1]}")
sys.exit(1 if failures else 0)
