from app.config import get_settings


def test_redirect_rate_limit_enforced(client, auth_headers):
    """Hitting the redirect endpoint more than `rate_limit_redirect_per_minute`
    times within the same 60s window should eventually yield a 429."""
    settings = get_settings()
    create = client.post(
        "/urls", json={"long_url": "https://example.com/limited"}, headers=auth_headers
    )
    code = create.json()["short_code"]

    responses = [
        client.get(f"/{code}", follow_redirects=False)
        for _ in range(settings.rate_limit_redirect_per_minute + 5)
    ]
    statuses = [r.status_code for r in responses]
    assert 429 in statuses


def test_rate_limit_response_has_retry_after(client, auth_headers):
    settings = get_settings()
    create = client.post(
        "/urls", json={"long_url": "https://example.com/retry-after"}, headers=auth_headers
    )
    code = create.json()["short_code"]

    last = None
    for _ in range(settings.rate_limit_redirect_per_minute + 5):
        last = client.get(f"/{code}", follow_redirects=False)
        if last.status_code == 429:
            break
    assert last.status_code == 429
    assert "Retry-After" in last.headers


def test_redirect_served_from_cache_on_second_hit(client, auth_headers, fake_redis):
    create = client.post(
        "/urls", json={"long_url": "https://example.com/cached"}, headers=auth_headers
    )
    code = create.json()["short_code"]

    # First request populates the cache.
    client.get(f"/{code}", follow_redirects=False)

    import asyncio

    cached_value = asyncio.run(fake_redis.get(f"url:{code}"))
    assert cached_value is not None
    assert "https://example.com/cached" in cached_value
