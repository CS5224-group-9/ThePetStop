# Backend agent guidance

These instructions apply to files under `backend/`. Read `README.md` and inspect the relevant code before making changes. The repository also has separate Next.js guidance in `frontend/AGENTS.md`.

## Project context

ThePetStop is a proposed pet service web app for Singaporean pet owners. The preliminary report describes three prototype areas:

- Pet profiles, including basic pet details, vaccination information, and private veterinary documents.
- A map and directory of pet shops and veterinary clinics, with location search and filtering.
- A marketplace where users can browse products, add them to a cart, and complete a simulated purchase.

Treat the report as product context, not evidence that a feature or integration already exists. Its AWS architecture (Cognito, Lambda, API Gateway, RDS, S3, CloudFront), AVS registry sync, OneMap geocoding, PayNow payments, advertising, commissions, invoices, and reconciliation are proposals or future work unless the repository implements them. The prototype explicitly excludes real advertising and commission collection. Do not add real payments or claim a service is integrated without a specific task and working configuration.

## Current backend

- Django project: `config/`; Django app: `api/`.
- API framework: Django REST Framework. `django-cors-headers` and `python-dotenv` are dependencies; confirm their settings and usage before relying on them.
- Local database: SQLite (`db.sqlite3`). PostgreSQL is a proposed deployment database, not the current local configuration.
- Dependency management: `uv`, `pyproject.toml`, and `uv.lock`. Use `uv add`/`uv remove` for dependency changes and commit both metadata files. Do not use `pip freeze` as the source of truth.
- Target Python version is specified in `pyproject.toml`; check it rather than assuming a version.

## Implementation guidelines

- Keep API behavior and Django settings within `backend/`; coordinate contract changes with the Next.js frontend when a task spans both directories.
- Build only the requested slice of the prototype. Prefer small Django models, migrations, DRF serializers/views, URL routes, and focused tests over speculative service scaffolding.
- Enforce authentication and object ownership on private pet profiles, vaccination records, and veterinary documents. Never expose another user's records through list or detail endpoints.
- Keep document uploads private; do not put medical or identity data in public URLs or logs. If adding AWS storage later, use short lived authorized access as appropriate to the design.
- Validate external facility data and distinguish unverified entries from AVS licensed facilities. Do not present stale or mock data as current official registry data.
- Keep checkout simulated until real payment work is explicitly requested. Never imply a simulated purchase charged a customer or created a real seller payout.
- Use environment variables for secrets and deployment settings. `python-dotenv` must be explicitly loaded if `.env` files are used; installing it alone does not load them. Do not commit `.env`, credentials, uploaded private files, `.venv`, or the local database.
- Add Django tests for new backend behavior, especially permissions, ownership boundaries, validation, and any state transitions. Frontend Jest guidance in the report does not replace Django backend tests.
- Create and commit migrations when models change. Avoid rewriting existing migrations or deleting data without an explicit reason.

## Working locally

From `backend/` in PowerShell:

```powershell
uv sync
uv run python .\manage.py check
uv run python .\manage.py migrate
uv run python .\manage.py test
uv run python .\manage.py runserver
```

Use `README.md` for the fuller setup guide. If a command cannot run in the current environment, report that limitation and the check that was attempted.
