"""Sign-in throttling and secret-key validation."""

import pytest
from pydantic import ValidationError


def register(client, admin_headers, username, password):
    response = client.post("/auth/register", headers=admin_headers, json={
        "username": username, "password": password, "role": "lawyer", "must_change_password": False})
    assert response.status_code == 200, response.text


def login(client, username, password):
    return client.post("/auth/login", json={"username": username, "password": password})


def test_repeated_failures_lock_the_account_for_that_address(client, admin_headers):
    from backend.auth import login_throttle

    register(client, admin_headers, "lockme", "Correct-pass-1")
    for attempt in range(login_throttle.max_failures):
        assert login(client, "lockme", f"wrong-{attempt}").status_code == 401

    locked = login(client, "lockme", "Correct-pass-1")
    assert locked.status_code == 429, "even the right password is refused while locked"
    assert int(locked.headers["Retry-After"]) > 0
    assert "Too many failed sign-in attempts" in locked.json()["detail"]

    events = client.get("/audit/logs", headers=admin_headers,
                        params={"username": "lockme", "status_filter": "locked"}).json()["events"]
    assert events and events[0]["details"]["reason"] == "too_many_failures"

    # Another address is unaffected, so an outsider can't lock a user out of their own machine.
    assert login_throttle.retry_after("lockme", "10.9.8.7") == 0
    login_throttle.reset("lockme", "testclient")
    assert login(client, "lockme", "Correct-pass-1").status_code == 200


def test_successful_sign_in_clears_earlier_failures(client, admin_headers):
    from backend.auth import login_throttle

    register(client, admin_headers, "typo-prone", "Correct-pass-2")
    for attempt in range(login_throttle.max_failures - 1):
        login(client, "typo-prone", f"oops-{attempt}")
    assert login(client, "typo-prone", "Correct-pass-2").status_code == 200
    for attempt in range(login_throttle.max_failures - 1):
        assert login(client, "typo-prone", f"again-{attempt}").status_code == 401
    assert login(client, "typo-prone", "Correct-pass-2").status_code == 200


def test_failures_expire_after_the_window(monkeypatch):
    import backend.auth as auth

    clock = [1_000.0]
    monkeypatch.setattr(auth.time, "time", lambda: clock[0])
    throttle = auth.LoginThrottle(max_failures=3, window_seconds=60)
    for _ in range(3):
        throttle.record_failure("Someone", "1.2.3.4")
    assert throttle.retry_after("someone", "1.2.3.4") > 0, "usernames are case-insensitive"
    clock[0] += 61
    assert throttle.retry_after("someone", "1.2.3.4") == 0


def test_lockout_is_reported_as_a_security_event():
    from backend.integrations import EventNotifier

    notifier = EventNotifier(n8n_url="http://example.invalid/hook")
    event = notifier.build_event("auth.login", "locked", "lockme", None, {"reason": "too_many_failures"}, "10.0.0.5")
    assert event["event"] == "security.login_locked"
    assert "blocked after repeated failures" in notifier.slack_text(event)


@pytest.mark.parametrize("secret", ["your-secret-key-here-change-this-in-production", "changeme", "short-key"])
def test_weak_secret_keys_are_rejected(secret):
    from backend.config import Settings

    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(secret_key=secret)


def test_strong_secret_key_is_accepted():
    from backend.config import Settings

    assert Settings(secret_key="a-long-random-value-0123456789").secret_key.startswith("a-long")
