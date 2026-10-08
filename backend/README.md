# ThePetStop Backend

The backend is a Django project that exposes APIs for the Next.js frontend.
Dependencies are managed with [uv](https://docs.astral.sh/uv/), and the local development database is SQLite.

## Requirements

- Windows 10 or later
- Python 3.13 or later
- PowerShell
- uv

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

## Database setup

Apply Django migrations:

```powershell
uv run python .\manage.py migrate
```

The development database is stored in `db.sqlite3`. It is ignored by Git and does not need to be created manually.

## Run the backend

Check the Django configuration:

```powershell
uv run python .\manage.py check
```

Start the development server:

```powershell
uv run python .\manage.py runserver
```

The backend will be available at <http://127.0.0.1:8000/>.

Keep the backend running in one terminal and run the frontend separately:

```powershell
cd ..\frontend
yarn dev
```

The frontend will be available at <http://localhost:3000/>.

## Project structure

```text
backend/
├── api/                 # Application code: models, views, and API logic
├── config/              # Project settings, URLs, ASGI, and WSGI configuration
├── manage.py            # Django command-line entry point
├── pyproject.toml       # Project metadata and dependencies
├── uv.lock              # Locked dependency versions
└── db.sqlite3           # Local development database
```

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

Format and lint with Ruff:

```powershell
uv run ruff format
uv run ruff check --fix
```

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

Do not commit secrets or production credentials. Store local secrets in `backend/.env` and add this file to `.gitignore`.

The project includes `python-dotenv` as a dependency. When environment variables are added to Django settings, load them explicitly with `load_dotenv()` before reading values from `os.environ`.

Example `.env` values:

```env
DJANGO_DEBUG=True
DJANGO_SECRET_KEY=replace-this-for-local-development
```

The current development settings use Django's generated secret key and `DEBUG = True`; these must be moved to environment variables before deployment.
