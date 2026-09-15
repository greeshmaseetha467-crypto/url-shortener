from datetime import datetime, timedelta, timezone


def test_create_short_url_authenticated(client, auth_headers):
    resp = client.post(
        "/urls", json={"long_url": "https://example.com/some/long/path"}, headers=auth_headers
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["long_url"] == "https://example.com/some/long/path"
    assert len(body["short_code"]) == 7
    assert body["short_url"].endswith(body["short_code"])
    assert body["click_count"] == 0


def test_create_short_url_anonymous_allowed(client):
    resp = client.post("/urls", json={"long_url": "https://example.com/anon"})
    assert resp.status_code == 201


def test_create_short_url_with_custom_alias(client, auth_headers):
    resp = client.post(
        "/urls",
        json={"long_url": "https://example.com/x", "custom_alias": "my-alias"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["short_code"] == "my-alias"


def test_duplicate_custom_alias_rejected(client, auth_headers):
    client.post(
        "/urls", json={"long_url": "https://example.com/x", "custom_alias": "dup"}, headers=auth_headers
    )
    resp = client.post(
        "/urls", json={"long_url": "https://example.com/y", "custom_alias": "dup"}, headers=auth_headers
    )
    assert resp.status_code == 409


def test_invalid_long_url_rejected(client, auth_headers):
    resp = client.post("/urls", json={"long_url": "not-a-url"}, headers=auth_headers)
    assert resp.status_code == 422


def test_list_urls_only_shows_owned(client, auth_headers):
    client.post("/urls", json={"long_url": "https://example.com/1"}, headers=auth_headers)
    client.post("/urls", json={"long_url": "https://example.com/2"}, headers=auth_headers)
    client.post("/urls", json={"long_url": "https://example.com/anon"})  # not owned

    resp = client.get("/urls", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2


def test_redirect_follows_to_long_url(client, auth_headers):
    create = client.post(
        "/urls", json={"long_url": "https://example.com/target"}, headers=auth_headers
    )
    code = create.json()["short_code"]

    resp = client.get(f"/{code}", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "https://example.com/target"


def test_redirect_unknown_code_404(client):
    resp = client.get("/does-not-exist", follow_redirects=False)
    assert resp.status_code == 404


def test_redirect_increments_click_count(client, auth_headers):
    create = client.post(
        "/urls", json={"long_url": "https://example.com/counted"}, headers=auth_headers
    )
    code = create.json()["short_code"]

    for _ in range(3):
        client.get(f"/{code}", follow_redirects=False)

    details = client.get(f"/urls/{code}", headers=auth_headers)
    assert details.json()["click_count"] == 3


def test_expired_url_returns_410(client, auth_headers):
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    create = client.post(
        "/urls",
        json={"long_url": "https://example.com/expired", "expires_at": past},
        headers=auth_headers,
    )
    code = create.json()["short_code"]

    resp = client.get(f"/{code}", follow_redirects=False)
    assert resp.status_code == 410


def test_deactivated_url_returns_410(client, auth_headers):
    create = client.post(
        "/urls", json={"long_url": "https://example.com/deactivate"}, headers=auth_headers
    )
    code = create.json()["short_code"]

    client.put(f"/urls/{code}", json={"is_active": False}, headers=auth_headers)
    resp = client.get(f"/{code}", follow_redirects=False)
    assert resp.status_code == 410


def test_update_url_requires_ownership(client, auth_headers):
    create = client.post(
        "/urls", json={"long_url": "https://example.com/owned"}, headers=auth_headers
    )
    code = create.json()["short_code"]

    other = client.post("/auth/register", json={"email": "[email protected]", "password": "password123"})
    assert other.status_code == 201
    login = client.post("/auth/login", data={"username": "[email protected]", "password": "password123"})
    other_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = client.put(f"/urls/{code}", json={"is_active": False}, headers=other_headers)
    assert resp.status_code == 404


def test_delete_url(client, auth_headers):
    create = client.post(
        "/urls", json={"long_url": "https://example.com/deleteme"}, headers=auth_headers
    )
    code = create.json()["short_code"]

    resp = client.delete(f"/urls/{code}", headers=auth_headers)
    assert resp.status_code == 204

    resp = client.get(f"/urls/{code}", headers=auth_headers)
    assert resp.status_code == 404
