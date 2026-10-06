# ThePetStop repository guidance

These instructions apply across this repository. For work inside a project directory, also read its local `AGENTS.md` and `README.md`.

## Project layout

- `frontend/` is the Next.js app. Follow `frontend/AGENTS.md` for its version-specific rules. Its dependency manager is Yarn (`yarn.lock`).
- `backend/` is the Django API. Follow `backend/AGENTS.md` for its domain, security, and development rules. Its dependency manager is uv (`pyproject.toml` and `uv.lock`).
- `.github/workflows/` contains repository automation. Check which project a workflow actually covers before changing commands or assuming a CI check exists.

## Shared workflow

- Make changes in the relevant directory. For work crossing the frontend and backend, keep request and response formats, URLs, authentication behavior, and error handling consistent on both sides.
- Check the current implementation before treating a feature in the preliminary report as complete. The report describes prototype goals and proposed architecture; it is not a record of deployed integrations.
- Use the dependency manager and lockfile already used by each project. Avoid introducing a second lockfile for the same project.
- Keep secrets, local databases, virtual environments, dependencies, and build artifacts out of Git. Follow the root and project `.gitignore` files; do not commit real credentials or private pet records.
- Add or update focused checks when changing behavior. Report the commands run and any checks that could not run.

## Useful commands

From `frontend/`: `yarn install`, `yarn lint`, `yarn build`, `yarn dev`.

From `backend/`: `uv sync`, `uv run python manage.py check`, `uv run python manage.py test`, `uv run python manage.py runserver`.
