# Backend agent guidance

These instructions apply to files under `backend/`. Read `README.md` and inspect the relevant code before making changes. The repository also has separate Next.js guidance in `frontend/AGENTS.md`.

## Project context

ThePetStop is a pet service web app for Singaporean pet owners. The MVP has three backend domains, one Django app each:

- `facilities`: AVS-licensed vets and pet shops with location search, verification source, and last-checked date.
- `pets`: pet profiles, allergies and diet, vaccination and care records, private vet reports, and reminders.
- `marketplace`: six fictional merchants, catalogue search and price comparison, a multi-merchant cart, simulated checkout split per merchant, order history, and merchant management.

Fuller context is in `../docs/`:

- `product-context.md` for scope;
- `architecture.md` for the AWS design, known gaps in `config/settings.py`, and open decisions;
- `data-model.md` for draft models and checkout rules;
- `repository-structure.md` for app boundaries and the API contract.

Treat the report and plan as product context, not evidence that a feature or integration already exists. Its AWS architecture (Cognito, Lambda, API Gateway, RDS, S3, CloudFront), AVS registry sync, OneMap geocoding, PayNow payments, advertising, commissions, invoices, and reconciliation are proposals or future work unless the repository implements them. The prototype explicitly excludes real advertising and commission collection. Do not add real payments or claim a service is integrated without a specific task and working configuration.

## Current backend

- Django project: `config/`; Django app: `api/`.
- API framework: Django REST Framework. `django-cors-headers` and `python-dotenv` are dependencies; confirm their settings and usage before relying on them.
- Local database: SQLite (`db.sqlite3`) today. The team has decided to move local development to PostgreSQL 16 in Docker Compose, read through `DATABASE_URL` (see `../docs/architecture.md`). Write code and queries that work on PostgreSQL, and do not add SQLite-only behaviour.
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
