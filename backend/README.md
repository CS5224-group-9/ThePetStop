# ThePetStop Backend

The backend is a Django project that exposes APIs for the Next.js frontend.
Dependencies are managed with [uv](https://docs.astral.sh/uv/). The local database is PostgreSQL 16, run in Docker Compose (see [../docs/architecture.md](../docs/architecture.md#decisions)). Each member has their own private database.

## Requirements

- Windows 10 or later
- Python 3.13 or later
- PowerShell
- uv
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) with the WSL 2 backend

Install uv in PowerShell if it is not already installed:

```powershell
irm https://astral.sh/uv/install.ps1 | iex
```

Restart PowerShell and verify the installation:

```powershell
uv --version
```

## Setup

From the repository root, enter the backend directory:

```powershell
cd backend
```

Install the dependencies and create/update the virtual environment:

```powershell
uv sync
```

`uv` uses `pyproject.toml` for the declared dependencies and `uv.lock` for reproducible versions. Do not commit `.venv/` or `.env` files.

Create your `.env` file. See [Environment variables](#environment-variables).

## Database setup

Start Docker Desktop, then start PostgreSQL from the **repository root**:

```powershell
docker compose up -d
docker compose ps    # wait until the db service is "healthy"
```

From `backend/`, apply the migrations and create an admin account for yourself:

```powershell
uv run python .\manage.py migrate
uv run python .\manage.py createsuperuser
```

The data lives in a Docker volume on your machine. It survives restarts and `docker compose down`. To start again from an empty database:

```powershell
docker compose down -v
docker compose up -d
uv run python .\manage.py migrate
```

### Troubleshooting

| Symptom | Fix |
| --- | --- |
| `error during connect ... dockerDesktopLinuxEngine` | Docker Desktop is not running. Start it and wait for "Engine running". |
| `password authentication failed for user "petstop"` | Another PostgreSQL (often a native Windows install) is using port 5432. Stop that service, or change the port in `docker-compose.yml` to `"5433:5432"` locally (don't commit it) and use `localhost:5433` in `DATABASE_URL`. |
| `KeyError: 'DJANGO_SECRET_KEY'` or `'DATABASE_URL'` | `backend/.env` is missing. Create it from `.env.example`. |
| `relation ... does not exist` | Run `migrate`. |

## Run the backend

Check the Django configuration:

```powershell
uv run python .\manage.py check
```

Start the development server:

```powershell
uv run python .\manage.py runserver
```

The backend will be available at <http://127.0.0.1:8000/>. Until Cognito sign-in exists, log in at <http://127.0.0.1:8000/admin/> with your superuser; private endpoints such as <http://127.0.0.1:8000/api/v1/me/> then use that session in the browser.

Keep the backend running in one terminal and run the frontend separately:

```powershell
cd ..\frontend
yarn dev
```

The frontend will be available at <http://localhost:3000/>.

## Project structure

```text
backend/
├── api/                 # Shared API code: error format, /health/
├── accounts/            # User model, /me/
├── pets/                # Feature 2 (workstream B)
├── facilities/          # Feature 1 (workstream C)
├── marketplace/         # Feature 3 (workstreams D1–D3; D2 owns migrations)
├── config/              # Project settings, URLs, ASGI, and WSGI configuration
├── manage.py            # Django command-line entry point
├── pyproject.toml       # Project metadata and dependencies
├── uv.lock              # Locked dependency versions
├── .env.example         # Environment variables, with placeholder values
└── .env                 # Your local values (ignored by Git)
```

All API routes are under `/api/v1/`. When a feature app adds its first routes, include its `urls.py` in `config/urls.py`.

## Common Django commands

Create a new application:

```powershell
uv run python .\manage.py startapp app_name
```

After changing models, create and apply migrations:

```powershell
uv run python .\manage.py makemigrations
uv run python .\manage.py migrate
```

Create an administrator account for Django Admin:

```powershell
uv run python .\manage.py createsuperuser
```

The admin site is available at <http://127.0.0.1:8000/admin/>.

Run tests:

```powershell
uv run python .\manage.py test
```

## Lint and format

[Ruff](https://docs.astral.sh/ruff/) is the linter and formatter. Its settings are in `pyproject.toml`, and migrations are excluded. CI runs these checks on every pull request, so run them before you push:

```powershell
uv run ruff check .
uv run ruff format --check .
uv run python .\manage.py check
```

Fix what Ruff can fix automatically, and reformat the code:

```powershell
uv run ruff check --fix .
uv run ruff format .
```

Fix the remaining findings by hand rather than silencing them with `# noqa`.

From the repository root, add `--directory backend`, for example `uv --directory backend run ruff check .`.

## Adding dependencies

Add a dependency with `uv` rather than installing it manually with `pip`:

```powershell
uv add package-name
```

For example:

```powershell
uv add psycopg[binary]
```

This updates `pyproject.toml` and `uv.lock`. Commit both files after changing dependencies.

## Environment variables

Do not commit secrets or production credentials. Store local secrets in `backend/.env`, which the root `.gitignore` already ignores.

Django reads its settings from environment variables, and `config/settings.py` loads `backend/.env` with `load_dotenv()`. `.env.example` lists every variable with placeholder values. Create your own copy:

```powershell
Copy-Item .env.example .env
```

Then generate a secret key and paste it into `.env` as `DJANGO_SECRET_KEY`:

```powershell
uv run python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

| Variable | Meaning |
| --- | --- |
| `DJANGO_SECRET_KEY` | Required. Generate your own; never reuse one from Git. |
| `DJANGO_DEBUG` | `True` locally. Anything else means off. |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hostnames. |
| `DJANGO_CORS_ALLOWED_ORIGINS` | Comma-separated origins allowed to call the API, such as the Next.js dev server. |
| `DATABASE_URL` | Required locally. Matches `docker-compose.yml` by default. |
| `COGNITO_ISSUER`, `COGNITO_CLIENT_ID` | Optional locally. Set them to the dev user pool (the `PetStop-Dev-Auth` stack outputs) to accept the frontend's bearer tokens; blank means only the admin session login works. |

In AWS, the `PetStop-Dev-Api` stack sets these instead: `DJANGO_SECRET_KEY_ARN` and `DB_SECRET_ARN` (secrets read at start-up, replacing `DJANGO_SECRET_KEY` and `DATABASE_URL`) and `COGNITO_JWKS` (the pool's public keys, because the Lambda has no internet access).

When you add a variable, add it to `.env.example` with a placeholder value in the same pull request.

### Marketplace catalogue

Load the committed fictional catalogue fixtures after applying migrations:

```powershell
uv run python .\manage.py load_catalogue
```

The command is idempotent. D2's three fixtures contain 24 products per shop; D3 can add shops 4–6 in additional shop-N.json files.

### OneMap location search (local development)

The facilities API contract is documented in [the facilities OpenAPI specification](../docs/openapi/facilities.yaml). It marks the implemented location search separately from the planned facility list and detail routes.

`GET /api/v1/locations/search/?q=Bishan` is public and independent of the facility registry. It returns `{"results":[{"label":"…","postal_code":"570001","latitude":1.35,"longitude":103.83}]}` (illustrative coordinates), or an empty results list. Queries must contain 2–120 characters. Results contain at most 10 unique valid locations from OneMap's first result page; this is not exhaustive pagination.

Register and confirm a OneMap account at <https://www.onemap.gov.sg/apidocs/register>. Optionally set an existing `ONEMAP_ACCESS_TOKEN` in your ignored `backend/.env`. Set `ONEMAP_EMAIL` and `ONEMAP_PASSWORD` to obtain replacement tokens automatically, then restart Django. Never put them in frontend variables. Without a usable token or renewal credentials, search returns a structured 503; no sample addresses are substituted. Basemap tiles and browser geolocation still work without these credentials.

The client authenticates using `/api/auth/post/getToken`, uses a supplied token until OneMap rejects it, keeps generated tokens in process memory until their reported expiry, and retries once with renewed authentication when search rejects the token (including OneMap's HTTP-200 error payload). HTTPS calls use a fixed host, a four-second socket timeout, bounded response size, and no redirect following. Upstream failure/timeout responses use the shared error contract and never include upstream bodies or credentials. Search is throttled to 30 requests per minute per client identity using Django's cache; this is a development/process-local guard, not a distributed production quota.

The address-search tests never call OneMap or require a database:

```powershell
uv run python manage.py test facilities.tests --noinput
```

The current production Django Lambda has no outbound internet access. Interactive OneMap search deployment remains PR 3 work; the local proxy does not change the VPC architecture.

### Facility ingestion reliability

The ingestion pipeline has durable S3 status events, database run/event history,
query checkpoints, bounded retries, reconciliation, failure queues and a review
gate for large deactivations. Apply migrations before updating the Lambda image.
Runs/events/facilities are available read-only in Django admin. The ingestion
tests require PostgreSQL; `uv run python manage.py test facilities.test_ingestion`
covers rollback, checkpoint recovery, duplicate delivery and review approval.
See [the operations runbook](../docs/facility-ingestion-operations.md) for the
isolated Floci suite, recovery commands, configuration and AWS release gate.

An existing token alone works until rejected. On rejection, the server obtains a new token using the configured email/password and retries the search once. The replacement is reused in memory; `.env` is never rewritten. After a process restart, the configured starting token is tried again. With no renewal credentials, replace the token manually and restart Django. Generated tokens with a known expired timestamp are renewed before the next search; no scheduled refresh job is required.
