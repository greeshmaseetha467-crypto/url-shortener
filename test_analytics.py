def _create_and_click(client, auth_headers, n_clicks=2):
    create = client.post(
        "/urls", json={"long_url": "https://example.com/tracked"}, headers=auth_headers
    )
    code = create.json()["short_code"]
    for _ in range(n_clicks):
        client.get(f"/{code}", follow_redirects=False, headers={"referer": "https://google.com"})
    return code


def test_analytics_summary_reflects_clicks(client, auth_headers):
    code = _create_and_click(client, auth_headers, n_clicks=3)

    resp = client.get(f"/analytics/{code}", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_clicks"] == 3
    assert body["short_code"] == code
    assert sum(day["count"] for day in body["clicks_by_day"]) == 3


def test_analytics_top_referrers(client, auth_headers):
    code = _create_and_click(client, auth_headers, n_clicks=2)

    resp = client.get(f"/analytics/{code}", headers=auth_headers)
    referrers = resp.json()["top_referrers"]
    assert any(r["referrer"] == "https://google.com" and r["count"] == 2 for r in referrers)


def test_raw_clicks_endpoint(client, auth_headers):
    code = _create_and_click(client, auth_headers, n_clicks=2)

    resp = client.get(f"/analytics/{code}/clicks", headers=auth_headers)
    assert resp.status_code == 200
    clicks = resp.json()
    assert len(clicks) == 2
    assert clicks[0]["referrer"] == "https://google.com"


def test_analytics_requires_ownership(client, auth_headers):
    create = client.post(
        "/urls", json={"long_url": "https://example.com/private"}, headers=auth_headers
    )
    code = create.json()["short_code"]

    other = client.post("/auth/register", json={"email": "[email protected]", "password": "password123"})
    login = client.post("/auth/login", data={"username": "[email protected]", "password": "password123"})
    other_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = client.get(f"/analytics/{code}", headers=other_headers)
    assert resp.status_code == 404


def test_analytics_unknown_code_404(client, auth_headers):
    resp = client.get("/analytics/does-not-exist", headers=auth_headers)
    assert resp.status_code == 404
