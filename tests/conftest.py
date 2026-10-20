"""Shared fixtures: run the API against an isolated, throwaway data directory."""

import os
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(scope="session")
def client(tmp_path_factory):
    workdir = tmp_path_factory.mktemp("legal-ai")
    os.chdir(workdir)  # data/, logs/ and analytics.db are resolved relative to cwd
    os.environ.update({
        "SECRET_KEY": "test-secret-key-not-for-production",
        "LLM_ENABLED": "false",
        "LOG_FILE": str(workdir / "logs" / "app.log"),
    })
    sys.path.insert(0, REPO_ROOT)

    from fastapi.testclient import TestClient
    from backend.app import app

    with TestClient(app) as test_client:
        yield test_client


ADMIN_PASSWORD = "Admin-Test-Pass-1"


@pytest.fixture(scope="session")
def admin_headers(client):
    """Sign in as the default admin and complete the forced first-login password change."""
    response = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user"]["must_change_password"] is True
    changed = client.post(
        "/auth/change-password",
        headers={"Authorization": f"Bearer {body['access_token']}"},
        json={"current_password": "admin123", "new_password": ADMIN_PASSWORD},
    )
    assert changed.status_code == 200, changed.text
    return {"Authorization": f"Bearer {changed.json()['access_token']}"}
