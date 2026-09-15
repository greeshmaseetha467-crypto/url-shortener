def test_register_creates_user(client):
    resp = client.post("/auth/register", json={"email": "[email protected]", "password": "password123"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "[email protected]"
    assert "hashed_password" not in body  # never leak the hash


def test_register_duplicate_email_rejected(client, registered_user):
    resp = client.post("/auth/register", json=registered_user)
    assert resp.status_code == 400


def test_register_short_password_rejected(client):
    resp = client.post("/auth/register", json={"email": "[email protected]", "password": "short"})
    assert resp.status_code == 422


def test_login_success_returns_token(client, registered_user):
    resp = client.post(
        "/auth/login",
        data={"username": registered_user["email"], "password": registered_user["password"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) > 10


def test_login_wrong_password_rejected(client, registered_user):
    resp = client.post(
        "/auth/login", data={"username": registered_user["email"], "password": "wrong-password"}
    )
    assert resp.status_code == 401


def test_login_unknown_user_rejected(client):
    resp = client.post("/auth/login", data={"username": "[email protected]", "password": "whatever"})
    assert resp.status_code == 401


def test_protected_endpoint_requires_token(client):
    resp = client.get("/urls")
    assert resp.status_code == 401


def test_protected_endpoint_with_token_succeeds(client, auth_headers):
    resp = client.get("/urls", headers=auth_headers)
    assert resp.status_code == 200
