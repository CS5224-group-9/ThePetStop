# PetStop

A web app for pet owners in Singapore, built as a CS5224 group project. The MVP covers verified discovery of AVS-licensed vets and pet shops, pet profiles with health records and reminders, and a multi-merchant marketplace with simulated checkout.

The project is at the scaffolding stage: the frontend and backend are set up, but no feature is implemented yet.

## Layout

- [frontend/](frontend/): Next.js app, managed with Yarn. See [frontend/README.md](frontend/README.md).
- [backend/](backend/): Django API, managed with uv. See [backend/README.md](backend/README.md).
- [docs/](docs/): project context.
  - [product-context.md](docs/product-context.md): MVP scope, out-of-scope items, and evaluation needs.
  - [architecture.md](docs/architecture.md): AWS architecture, current state, and decisions.
  - [data-model.md](docs/data-model.md): draft models and the seed catalogue format.
  - [repository-structure.md](docs/repository-structure.md): target layout and API contract.
  - [roadmap.md](docs/roadmap.md): milestones and workstream owners.

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
