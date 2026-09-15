# URL Shortener + Analytics Platform

A production-style Bitly clone: short URLs, redirects, click analytics, JWT
auth, Redis caching, and Redis-backed rate limiting — built with FastAPI,
PostgreSQL, and Redis, fully Dockerized.

## Features

- **Short URL creation** with optional custom aliases and expiration dates
- **Fast redirects** (`GET /{short_code}`) cached in Redis to avoid a DB hit
  on every click
- **JWT authentication** — URLs can be created anonymously, but listing,
  editing, deleting, and analytics require an owned, authenticated account
- **Click analytics**: total clicks, clicks-by-day, top referrers, top user
  agents, and a raw click log
- **Rate limiting** per client (token or IP) via a Redis fixed-window
  counter, with separate limits for the high-traffic redirect route vs. the
  general API
- **PostgreSQL** for durable storage, **Redis** for caching + rate limiting
- **Auto-generated OpenAPI docs** at `/docs` and `/redoc`
- **Unit + integration tests** (pytest, SQLite + fakeredis, no external
  services required)
- **Docker Compose** stack: API + Postgres + Redis

## Architecture

```
Client → FastAPI app
           ├── /auth/*        → Postgres (users)
           ├── /urls/*        → Postgres (urls), Redis cache invalidation
           ├── /analytics/*   → Postgres (clicks aggregation)
           └── /{short_code}  → Redis (cache) → Postgres (fallback + click log)
```

**Redirect hot path**: on a cache hit, resolving `short_code → long_url` is
a single Redis `GET` — no database round trip. Click logging still writes
to Postgres synchronously for durability; at very high scale this would
move to an async queue (Kafka / Redis Streams) so click writes never block
the redirect response — see "Scaling further" below.

**Rate limiting**: a Redis fixed-window counter (`INCR` + `EXPIRE`) keyed by
bearer token (if present) or IP, scoped separately for `api` (general CRUD),
`auth` (register/login, to slow down credential stuffing), and `redirect`
(much higher limit, since this is the public, high-traffic path).

## Project layout

```
app/
  main.py            FastAPI app, router wiring, lifespan (table creation)
  config.py          Settings (env-var driven, pydantic-settings)
  database.py        SQLAlchemy engine/session
  models.py          User, URL, Click ORM models
  schemas.py         Pydantic request/response models
  auth.py            Password hashing, JWT issuing/validation
  redis_client.py    Redis connection pool / dependency
  rate_limiter.py    Redis fixed-window rate limit dependency
  utils.py           Short code generation
  crud.py            DB access layer
  routers/
    auth.py          POST /auth/register, /auth/login
    urls.py          POST/GET/PUT/DELETE /urls
    analytics.py     GET /analytics/{code}, /analytics/{code}/clicks
    redirect.py       GET /{short_code}
tests/               pytest suite (SQLite + fakeredis, no external services)
Dockerfile
docker-compose.yml
requirements.txt
.env.example
```

## Running locally with Docker (recommended)

```bash
cp .env.example .env     # edit SECRET_KEY etc. as needed
docker compose up --build
```

The API is now available at `http://localhost:8000`, with interactive docs
at `http://localhost:8000/docs`.

## Running locally without Docker

Requires local PostgreSQL and Redis instances.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env     # point DATABASE_URL / REDIS_URL at your local services
uvicorn app.main:app --reload
```

## Running the tests

The test suite requires **no external services** — it uses an on-disk
SQLite database and `fakeredis` in place of Postgres/Redis.

```bash
pip install -r requirements.txt
pytest
```

## API overview

| Method | Path                        | Auth              | Description                          |
|--------|-----------------------------|-------------------|---------------------------------------|
| POST   | `/auth/register`            | none              | Create an account                     |
| POST   | `/auth/login`                | none              | Get a JWT access token                |
| POST   | `/urls`                     | optional          | Create a short URL                    |
| GET    | `/urls`                     | required          | List your short URLs                  |
| GET    | `/urls/{short_code}`        | required (owner)  | Get details of one of your URLs       |
| PUT    | `/urls/{short_code}`        | required (owner)  | Update long URL / expiry / active flag |
| DELETE | `/urls/{short_code}`        | required (owner)  | Delete a short URL                    |
| GET    | `/analytics/{short_code}`   | required (owner)  | Aggregated click analytics            |
| GET    | `/analytics/{short_code}/clicks` | required (owner) | Raw click log (paginated)         |
| GET    | `/{short_code}`             | none              | Redirect to the long URL              |
| GET    | `/health`                   | none              | Liveness/readiness probe              |

Full request/response schemas are available at `/docs` (Swagger UI) once
the app is running.

### Example: create and use a short URL

```bash
# Register
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "[email protected]", "password": "supersecret123"}'

# Login
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -d "username=you@example.com&password=supersecret123" | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# Create a short URL
curl -X POST http://localhost:8000/urls \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"long_url": "https://example.com/some/very/long/path", "custom_alias": "my-link"}'

# Use it
curl -i http://localhost:8000/my-link

# View analytics
curl http://localhost:8000/analytics/my-link -H "Authorization: Bearer $TOKEN"
```

## Design decisions & tradeoffs

- **Denormalized `click_count`** on the `urls` table gives O(1) reads for
  simple counts (e.g. dashboard lists), while the `clicks` table retains
  the full event log for detailed analytics (time series, referrers, user
  agents).
- **Anonymous URL creation** is allowed (common in real shorteners), but
  anonymous links have no owner and can't be listed, edited, or analyzed —
  only redirected through.
- **Fixed-window rate limiting** was chosen for simplicity and O(1) cost
  per request. It allows brief bursts at window boundaries; a sliding-log
  or token-bucket algorithm could be swapped in behind the same
  `rate_limit()` dependency if stricter smoothing is required.
- **`Base.metadata.create_all`** is used at startup for simplicity/dev
  convenience and to keep the test suite dependency-free. A real production
  deployment should manage schema changes with **Alembic migrations**
  instead of relying on `create_all`.

## Scaling further (not implemented here, but the natural next steps)

- Move click-event writes off the request path onto a queue (Kafka / Redis
  Streams / SQS) with a separate consumer batch-inserting into Postgres,
  so a slow analytics write never adds latency to a redirect.
- Partition/shard the `clicks` table (e.g. by month) once volume grows.
- Add a read replica for analytics queries so they don't compete with the
  hot redirect path for Postgres connections.
- Replace the fixed-window rate limiter with a Redis Lua-scripted
  sliding-window or token-bucket for smoother throttling.
- Put a CDN/edge cache (e.g. Cloudflare Workers) in front of the redirect
  route for the most popular links to cut latency further and offload
  origin traffic entirely.
