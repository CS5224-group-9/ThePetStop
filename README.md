# PetStop

A web app for pet owners in Singapore, built as a CS5224 group project. The prototype covers pet profiles with vaccination records, a map and directory of AVS-licensed pet shops and veterinary clinics, and a marketplace with simulated checkout.

The project is at the scaffolding stage: the frontend and backend are set up, but no feature is implemented yet.

## Layout

- [frontend/](frontend/): Next.js app, managed with Yarn. See [frontend/README.md](frontend/README.md).
- [backend/](backend/): Django API, managed with uv. See [backend/README.md](backend/README.md).
- [docs/](docs/): project context.
  - [product-context.md](docs/product-context.md): prototype scope and evaluation plan.
  - [architecture.md](docs/architecture.md): proposed AWS architecture, current state, and open decisions.
  - [repository-structure.md](docs/repository-structure.md): current and draft target layout.

## Running locally

Backend, from `backend/`:

```powershell
uv sync
uv run python .\manage.py migrate
uv run python .\manage.py runserver
```

Frontend, from `frontend/`:

```powershell
yarn install
yarn dev
```

The backend serves <http://127.0.0.1:8000/> and the frontend <http://localhost:3000/>.

## Code style

Formatting is automatic: Prettier for the frontend, Ruff for the backend. The `Lint and Format` workflow checks both on every pull request.

Before pushing, from `frontend/`:

```powershell
yarn format
yarn lint
```

And from `backend/`:

```powershell
uv run ruff format
uv run ruff check --fix
```

In VS Code, install the recommended extensions when prompted and files are formatted on save. Line endings are LF on every OS, set in `.gitattributes` and `.editorconfig`.
