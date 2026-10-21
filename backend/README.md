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
