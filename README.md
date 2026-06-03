# HS Codes API

![CI](https://github.com/DigitalTouchCode/Hs_codes_api/actions/workflows/ci.yml/badge.svg)
![Deploy](https://github.com/DigitalTouchCode/Hs_codes_api/actions/workflows/deploy.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.12-blue.svg)
![Django](https://img.shields.io/badge/django-6.0-092E20?logo=django)
![PostgreSQL](https://img.shields.io/badge/postgresql-16-336791?logo=postgresql)
![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)
![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)

A public REST API for searching ZIMRA Harmonised System (HS) codes using trigram similarity. The search endpoint is open — uploading HS code data is internal and not part of the public API.

**Live:** https://tools.digitaltouch.co.zw

## Features

- Fuzzy search across HS code and description using PostgreSQL trigram similarity
- Configurable similarity threshold
- Throttling on all endpoints
- Health check endpoint

## Requirements

- Python 3.12
- PostgreSQL 16
- Docker & Docker Compose (for containerised setup)

## Local Setup

**1. Clone and create a virtual environment**
```bash
git clone git@github.com:DigitalTouchCode/Hs_codes_api.git
cd Hs_codes_api
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**2. Configure environment**
```bash
cp .env.example .env
```

Edit `.env`:
```env
SECRET_KEY=your-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=postgres://hsuser:hspass@localhost:5432/hsdb
HS_CODE_SEARCH_THRESHOLD=0.1
```

**3. Run migrations**
```bash
python manage.py migrate
```

**4. Run the development server**
```bash
DJANGO_SETTINGS_MODULE=core.settings.development python manage.py runserver
```

## Docker Setup

```bash
cp .env.example .env  # fill in values
docker compose up -d --build
```

The API will be available at `http://localhost:8001`.

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `SECRET_KEY` | Yes | — | Django secret key |
| `DEBUG` | Yes | — | `True` or `False` |
| `ALLOWED_HOSTS` | Yes | — | Comma-separated hostnames |
| `DATABASE_URL` | Yes | — | PostgreSQL connection string |
| `HS_CODE_SEARCH_THRESHOLD` | No | `0.1` | Minimum trigram similarity score (0–1) |
| `GUNICORN_WORKERS` | No | `3` | Number of Gunicorn worker processes |

## API Reference

### Search HS Codes

`GET /api/v1/hs-codes/?q=<query>`

Search HS codes by description or code using trigram similarity. Results are ordered by relevance, with description weighted 2× higher than the code.

**Parameters**

| Parameter | Required | Description |
|---|---|---|
| `q` | Yes | Search term |

**Response `200`**
```json
[
  {
    "id": 1,
    "hs_code": "8471.30.00",
    "description": "Portable automatic data processing machines",
    "created_at": "2026-01-01T00:00:00Z",
    "hs_code_file": 1
  }
]
```

**Response `400` — missing query**
```json
{"q": ["This query parameter is required."]}
```

### Health Check

`GET /api/v1/health/`

**Response `200`**
```json
{"status": "healthy"}
```

## Code Formatting

This project uses [Black](https://black.readthedocs.io/) for code formatting, enforced via pre-commit.

**Install pre-commit hooks**
```bash
pip install pre-commit
pre-commit install
```

**Run manually**
```bash
black .
```

**Check without modifying**
```bash
black --check .
```

Black is pinned at `24.8.0` in `.pre-commit-config.yaml`.

## Tests

**Run all tests**
```bash
python manage.py test app
```

**Run a specific test class**
```bash
python manage.py test app.tests.HsCodeUploadViewTest
```

**Run a single test**
```bash
python manage.py test app.tests.HsCodeUploadViewTest.test_upload_valid_csv_returns_201
```

**Test coverage by area**

| Area | Tests |
|---|---|
| File decoding | UTF-8, BOM stripping, bad encoding |
| CSV parsing | Valid CSV, missing columns, empty file |
| Object building | Blank row skipping, whitespace trimming |
| Upload service | Full flow, duplicates, partial duplicates |
| Upload view | 201/400 responses, duplicate handling |
| Search view | Missing `q`, fuzzy match, no results |
| Health check | 200 response, no auth required |
| Model | Unique constraint, cascade delete |
| Permissions | Admin/Staff allowed, unknown role/unauthenticated denied |

## Deployment

Deployment is handled via GitHub Actions. On every push to `main`:

1. The **CI** workflow runs all 40 tests against a PostgreSQL service container.
2. On CI success, the **Deploy Production** workflow SSHs into the VPS and deploys the latest build.

**Required GitHub Secrets**

| Secret | Description |
|---|---|
| `VPS_HOST` | VPS IP or hostname |
| `VPS_USER` | SSH username |
| `VPS_SSH_KEY` | Private SSH key |
| `VPS_PORT` | SSH port (usually `22`) |

The deploy script polls `GET /api/v1/health/` for up to 100 seconds after startup before marking the deployment as succeeded or failed.
