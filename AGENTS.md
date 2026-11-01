# ThePetStop repository guidance

These instructions apply across this repository. For work inside a project directory, also read its local `AGENTS.md` and `README.md`.

## Product

ThePetStop is a CS5224 group project: a web app for pet owners in Singapore, deployed on AWS. The MVP, due Wed 11 Nov 2026, has three features:

1. **Verified facility discovery**: a map and searchable directory of AVS-licensed vets and pet shops, with filters, details, directions, and the verification source and last-checked date.
2. **Pet profiles**: multiple pets per user; allergies and diet; vaccination and care records; private vet reports; in-app reminders. Each owner sees only their own pets.
3. **Multi-merchant marketplace**: six fictional shops; search, filters and price comparison; one cart and checkout across merchants with simulated payment; order history; basic merchant management.

Real payments, ledgers and invoices, commission, advertising, booking, email and SMS notifications, and pet parks are out of scope. Do not build them without a team decision. The full list is in `docs/product-context.md`.

## Context files

Read the one that matches the task; they are not loaded automatically.

- `docs/product-context.md`: MVP scope, what is out of scope, and what the evaluation needs from the code.
- `docs/architecture.md`: the AWS architecture, the current state of the code, and decisions made and still open.
- `docs/data-model.md`: draft Django models, checkout rules, and the seed catalogue format.
- `docs/repository-structure.md`: target layout, app boundaries, and the API contract.
- `docs/roadmap.md`: milestones, workstream owners, and what must happen before Sprint 1.

## Project layout

- `frontend/` is the Next.js app. Follow `frontend/AGENTS.md` for its version-specific rules. Its dependency manager is Yarn (`yarn.lock`).
- `backend/` is the Django API. Follow `backend/AGENTS.md` for its domain, security, and development rules. Its dependency manager is uv (`pyproject.toml` and `uv.lock`).
- `docs/` holds the context files listed above. Update them when a decision is made or the implemented state changes.
- `.github/workflows/` contains repository automation. Check which project a workflow actually covers before changing commands or assuming a CI check exists. `backend-ci.yml` runs lint/format, Django checks/tests with PostgreSQL, and an isolated Floci recovery suite; frontend and infra workflows run their checks and tests on every pull request and push to `main`. `deploy.yml` deploys `main` to the dev stage (see `infra/README.md`); `aws-test.yml` is a manually triggered AWS connection check. Facility ingestion is opt-in CDK with schedules disabled until AWS acceptance.

## Sources versus repository

The preliminary report, the MVP scope brief, and the MVP Development Plan describe goals and a proposed design; they are not a record of what is built. Check the code before treating a feature as complete. Where they disagree with the repository, the repository wins:

- The report proposes one Lambda service per domain. The backend is a single Django project, deployed as one Lambda function; the plan agrees.
- The report says "React frontend". The frontend is Next.js; the plan agrees.
- The report names Jest for all tests. Backend tests use Django's test runner; Jest is for the frontend only.
- PostgreSQL, Cognito, S3, OneMap, and MapLibre are planned but not yet configured or installed.

Open decisions are listed in `docs/architecture.md`. Raise one with the user instead of settling it inside an unrelated change.

## Shared workflow

- Make changes in the relevant directory. For work crossing the frontend and backend, keep request and response formats, URLs, authentication behavior, and error handling consistent on both sides.
- Use the dependency manager and lockfile already used by each project. Avoid introducing a second lockfile for the same project.
- Keep secrets, local databases, virtual environments, dependencies, and build artifacts out of Git. Follow the root and project `.gitignore` files; do not commit real credentials or private pet records.
- Add or update focused checks when changing behavior. Report the commands run and any checks that could not run.

## Useful commands

From `frontend/`: `yarn install`, `yarn lint`, `yarn format` (or `yarn format:check`), `yarn build`, `yarn dev`.

From `infra/`: `yarn install`, `yarn format` (or `yarn format:check`), `yarn build`, `yarn test`, `yarn cdk diff`. Deploying needs AWS credentials; see `infra/README.md`.

From `backend/`: `uv sync`, `uv run ruff check .`, `uv run ruff format .`, `uv run python manage.py check`, `uv run python manage.py test`, `uv run python manage.py runserver`.
