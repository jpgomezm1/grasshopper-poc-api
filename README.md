# Grasshopper Backend

FastAPI backend for the Grasshopper vocational orientation platform.

## Setup

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in values
alembic upgrade head
uvicorn app.main:app --reload
```

## Required env vars for production

The following env vars MUST be set before deploying to production (Heroku).
The app will raise `RuntimeError` at boot and refuse to start if they are missing
or contain the default placeholder values.

### JWT_SECRET_KEY

Strong secret for signing JWT tokens. The default POC value is rejected in production.

```bash
# Generate:
python -c "import secrets; print(secrets.token_urlsafe(64))"

# Set in Heroku:
heroku config:set JWT_SECRET_KEY=<output> -a grasshopper-api

# Verify:
heroku config:get JWT_SECRET_KEY -a grasshopper-api
```

### FIELD_ENCRYPTION_KEY

AES-256-GCM key (32 bytes, base64-urlsafe encoded) for at-rest encryption of
`clinical_analysis_cache` and other sensitive JSONB columns. Required by
Ley 1581/2012 art. 5 (datos sensibles) and Ley 1090/2006 (datos clínicos).

```bash
# Generate:
python -c "import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"

# Set in Heroku:
heroku config:set FIELD_ENCRYPTION_KEY=<output> -a grasshopper-api
```

After setting the key, run the data migration to encrypt existing rows:

```bash
heroku run python -c "
from app.db.database import SessionLocal
from app.db.models import User
db = SessionLocal()
rows = db.query(User).filter(User.clinical_analysis_cache.isnot(None)).all()
for u in rows:
    u.clinical_analysis_cache_enc = u.clinical_analysis_cache
    u.clinical_analysis_cache = None
db.commit(); db.close()
print(f'Migrated {len(rows)} rows')
" -a grasshopper-api
```

### ALLOWED_ORIGINS_STR

Comma-separated list of allowed frontend origins. Used to validate `Origin`
headers in invitation-link generation (prevents open-redirect phishing).

```
ALLOWED_ORIGINS_STR=https://grasshopper-app.netlify.app,http://localhost:5173
```

Default (if not set):
```
https://grasshopper-app.netlify.app,http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173
```

### FRONTEND_BASE_URL

Canonical frontend URL used as the ultimate safe fallback when the `Origin`
header is missing or not in the whitelist.

```
FRONTEND_BASE_URL=https://grasshopper-app.netlify.app
```

## Other env vars

| Var | Required | Description |
|-----|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection string (Neon) |
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key for AI features |
| `OPENAI_API_KEY` | Yes | OpenAI Whisper transcription |
| `ENVIRONMENT` | Yes | `production` or `development` |
| `SENTRY_DSN_BACKEND` | No | Sentry DSN — omit to disable |
| `RESEND_API_KEY` | No | Transactional email — omit for stub mode |
| `BITRIX_WEBHOOK_URL` | No | Bitrix CRM sync — omit for stub mode |

## Running tests

```bash
pytest tests/ -q
```

Note: integration tests that use the PostgreSQL UUID type require a real
PostgreSQL connection. Most tests use unit/mock patterns and run without a DB.
