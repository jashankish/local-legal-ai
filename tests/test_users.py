"""User administration, forced password changes and session revocation."""


def login(client, username, password):
    return client.post("/auth/login", json={"username": username, "password": password})


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def create_user(client, admin_headers, username, password="Temp-pass-123", role="lawyer", must_change=True):
    response = client.post("/auth/register", headers=admin_headers, json={
        "username": username, "password": password, "email": f"{username}@firm.local",
        "role": role, "must_change_password": must_change,
    })
    assert response.status_code == 200, response.text
    return response


def test_new_user_must_change_password_before_using_the_api(client, admin_headers):
    create_user(client, admin_headers, "new.hire")
    body = login(client, "new.hire", "Temp-pass-123").json()
    assert body["user"]["must_change_password"] is True
    pending = bearer(body["access_token"])

    blocked = client.get("/documents", headers=pending)
    assert blocked.status_code == 403
    assert "Password change required" in blocked.json()["detail"]
    assert client.get("/auth/me", headers=pending).json()["must_change_password"] is True

    weak = client.post("/auth/change-password", headers=pending,
                       json={"current_password": "Temp-pass-123", "new_password": "short"})
    assert weak.status_code == 400
    wrong = client.post("/auth/change-password", headers=pending,
                        json={"current_password": "nope-nope-1", "new_password": "Brand-new-pass-1"})
    assert wrong.status_code == 400

    changed = client.post("/auth/change-password", headers=pending,
                          json={"current_password": "Temp-pass-123", "new_password": "Brand-new-pass-1"})
    assert changed.status_code == 200
    fresh = bearer(changed.json()["access_token"])
    assert client.get("/documents", headers=fresh).status_code == 200
    # The token issued before the change is revoked.
    assert client.get("/auth/me", headers=pending).status_code == 401


def test_admin_lists_and_updates_users(client, admin_headers):
    create_user(client, admin_headers, "paralegal1", role="user", must_change=False)
    listing = client.get("/users", headers=admin_headers).json()
    entry = next(u for u in listing["users"] if u["username"] == "paralegal1")
    assert entry["role"] == "user"
    assert "hashed_password" not in entry and "token_version" not in entry

    updated = client.patch("/users/paralegal1", headers=admin_headers, json={"role": "lawyer"}).json()
    assert updated["user"]["role"] == "lawyer"
    assert client.patch("/users/paralegal1", headers=admin_headers,
                        json={"role": "partner"}).status_code == 400
    assert client.patch("/users/ghost", headers=admin_headers, json={"role": "user"}).status_code == 404


def test_disabling_a_user_revokes_their_session(client, admin_headers):
    create_user(client, admin_headers, "contractor", password="Contract-pass-1", must_change=False)
    token = login(client, "contractor", "Contract-pass-1").json()["access_token"]
    assert client.get("/documents", headers=bearer(token)).status_code == 200

    client.patch("/users/contractor", headers=admin_headers, json={"is_active": False})
    assert client.get("/documents", headers=bearer(token)).status_code == 401
    assert login(client, "contractor", "Contract-pass-1").status_code == 403

    client.patch("/users/contractor", headers=admin_headers, json={"is_active": True})
    assert login(client, "contractor", "Contract-pass-1").status_code == 200


def test_admin_password_reset_forces_change(client, admin_headers):
    create_user(client, admin_headers, "forgetful", password="Original-pass-1", must_change=False)
    old_token = login(client, "forgetful", "Original-pass-1").json()["access_token"]

    reset = client.post("/users/forgetful/reset-password", headers=admin_headers,
                        json={"new_password": "Temporary-pass-9"})
    assert reset.status_code == 200
    assert client.get("/auth/me", headers=bearer(old_token)).status_code == 401
    assert login(client, "forgetful", "Original-pass-1").status_code == 401
    assert login(client, "forgetful", "Temporary-pass-9").json()["user"]["must_change_password"] is True


def test_last_admin_cannot_be_removed_and_self_disable_is_blocked(client, admin_headers):
    assert client.patch("/users/admin", headers=admin_headers,
                        json={"is_active": False}).status_code == 400
    response = client.patch("/users/admin", headers=admin_headers, json={"role": "lawyer"})
    assert response.status_code == 400
    assert "administrator" in response.json()["detail"]


def test_user_admin_requires_admin_role(client, admin_headers):
    create_user(client, admin_headers, "junior", password="Junior-pass-1", role="user", must_change=False)
    user_headers = bearer(login(client, "junior", "Junior-pass-1").json()["access_token"])
    assert client.get("/users", headers=user_headers).status_code == 403
    assert client.patch("/users/junior", headers=user_headers, json={"role": "admin"}).status_code == 403


def test_registration_validates_username_and_password(client, admin_headers):
    bad_name = client.post("/auth/register", headers=admin_headers,
                           json={"username": "a b", "password": "Valid-pass-1"})
    assert bad_name.status_code == 400
    same_as_name = client.post("/auth/register", headers=admin_headers,
                               json={"username": "samesame", "password": "samesame"})
    assert same_as_name.status_code == 400


def test_user_events_are_audited(client, admin_headers):
    events = client.get("/audit/logs", headers=admin_headers, params={"limit": 200}).json()["events"]
    actions = {e["action"] for e in events}
    assert {"user.create", "user.update", "user.password_reset", "auth.password_change"} <= actions
