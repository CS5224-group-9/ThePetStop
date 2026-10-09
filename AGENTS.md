# ThePetStop repository guidance

These instructions apply across this repository. For work inside a project directory, also read its local `AGENTS.md` and `README.md`.

## Product

ThePetStop is a CS5224 group project: a web app for pet owners in Singapore, planned for deployment on AWS. The prototype has three features:

1. **Pet profiles**: pet details, vaccination information, and private veterinary documents, visible only to the owner.
2. **Facility map and directory**: AVS-licensed pet shops and veterinary clinics, searched by location, radius, and category.
3. **Marketplace**: browse products, add to cart, and complete a simulated payment.

Advertising, commission collection, real payments, invoicing, reconciliation, service booking, and notifications are not part of the prototype. Do not build them without a specific task.

## Context files

Read the one that matches the task; they are not loaded automatically.

- `docs/product-context.md`: what the preliminary report asks for, what is out of scope, and what the evaluation plan requires of the code.
- `docs/architecture.md`: the proposed AWS architecture, what is implemented today, and the open decisions between the two.
- `docs/repository-structure.md`: current layout, draft target layout, draft API routes, and suggested order of work.

## Project layout

- `frontend/` is the Next.js app. Follow `frontend/AGENTS.md` for its version-specific rules. Its dependency manager is Yarn (`yarn.lock`).
- `backend/` is the Django API. Follow `backend/AGENTS.md` for its domain, security, and development rules. Its dependency manager is uv (`pyproject.toml` and `uv.lock`).
- `docs/` holds the context files listed above. Update them when a decision is made or the implemented state changes.
- `.github/workflows/` contains repository automation. Check which project a workflow actually covers before changing commands or assuming a CI check exists. `lint.yml` checks formatting and lint for both projects on pull requests and on pushes to `main`; `aws-test.yml` is a manually triggered AWS connection check. No workflow runs build or tests.

## Report versus repository

The preliminary report describes prototype goals and a proposed architecture; it is not a record of deployed integrations. Check the current implementation before treating a feature as complete. Where the two disagree, the repository is what exists:

- The report proposes one AWS Lambda service per feature. The backend is a single Django project, to be deployed as one Lambda function.
- The report says "React frontend". The frontend is Next.js.
- The report names Jest for frontend and backend tests. Backend tests use Django's test runner; the frontend has no test runner yet.
- The report proposes PostgreSQL, Cognito, S3, OneMap, and MapLibre. None is configured or installed.

Authentication, frontend hosting, and several other choices are still open. They are listed in `docs/architecture.md`. Raise an open decision with the user instead of settling it inside an unrelated change.

## Shared workflow

- Make changes in the relevant directory. For work crossing the frontend and backend, keep request and response formats, URLs, authentication behavior, and error handling consistent on both sides.
- Use the dependency manager and lockfile already used by each project. Avoid introducing a second lockfile for the same project.
- Keep secrets, local databases, virtual environments, dependencies, and build artifacts out of Git. Follow the root and project `.gitignore` files; do not commit real credentials or private pet records.
- Format and lint before finishing a change: Prettier and ESLint in `frontend/`, Ruff in `backend/`. CI rejects unformatted code. Line endings are LF (`.gitattributes`, `.editorconfig`).
- Add or update focused checks when changing behavior. Report the commands run and any checks that could not run.

## Useful commands

From `frontend/`: `yarn install`, `yarn format`, `yarn format:check`, `yarn lint`, `yarn build`, `yarn dev`.

From `backend/`: `uv sync`, `uv run ruff format`, `uv run ruff check --fix`, `uv run python manage.py check`, `uv run python manage.py test`, `uv run python manage.py runserver`.
