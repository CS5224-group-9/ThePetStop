# PetStop

A web app for pet owners in Singapore, built as a CS5224 group project. The MVP covers verified discovery of AVS-licensed vets and pet shops, pet profiles with health records and reminders, and a multi-merchant marketplace with simulated checkout.

The backend foundation (settings, PostgreSQL, user model, `/health/` and `/me/`) is in place. Pet profiles and the marketplace catalogue are implemented; see [docs/architecture.md](docs/architecture.md) for the current state.

## Layout

- [frontend/](frontend/): Next.js app, managed with Yarn. See [frontend/README.md](frontend/README.md).
- [backend/](backend/): Django API, managed with uv. See [backend/README.md](backend/README.md).
- [infra/](infra/): AWS CDK app in TypeScript, managed with Yarn. See [infra/README.md](infra/README.md) for AWS sign-in and deploy steps.
- [docs/](docs/): project context.
  - [product-context.md](docs/product-context.md): MVP scope, out-of-scope items, and evaluation needs.
  - [architecture.md](docs/architecture.md): AWS architecture, current state, and decisions.
  - [data-model.md](docs/data-model.md): draft models and the seed catalogue format.
  - [repository-structure.md](docs/repository-structure.md): target layout and API contract.
  - [roadmap.md](docs/roadmap.md): milestones and workstream owners.

## Running locally

Database, from the repository root (needs Docker Desktop running):

```powershell
docker compose up -d
```

PostgreSQL listens on `127.0.0.1:5432`. If that port is taken, set `PETSTOP_DB_PORT` in the shell or in a root `.env` (see [.env.example](.env.example)) and use the same port in `backend/.env` `DATABASE_URL`.

Backend, from `backend/`. The first time, create `.env` as described in [backend/README.md](backend/README.md#environment-variables).

```powershell
uv sync
uv run python .\manage.py migrate
uv run python .\manage.py seed_pets
uv run python .\manage.py runserver
```

`seed_pets` adds demo pets, records and reminders for the local dev users. For the offline dev sign-in, or to sign in through the real Cognito pool, follow [Run pet profiles locally](backend/README.md#run-pet-profiles-locally).

Frontend, from `frontend/`:

```powershell
yarn install
yarn dev
```

The backend serves <http://127.0.0.1:8000/> and the frontend <http://localhost:3000/>.
