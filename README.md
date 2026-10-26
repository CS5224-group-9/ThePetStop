# PetStop

A web app for pet owners in Singapore, built as a CS5224 group project. The MVP covers verified discovery of AVS-licensed vets and pet shops, pet profiles with health records and reminders, and a multi-merchant marketplace with simulated checkout.

The project is at the scaffolding stage: the backend foundation (settings, PostgreSQL, user model, `/health/` and `/me/`) is in place, but no feature is implemented yet.

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

To run Floci with PostgreSQL for local facility-ingestion work, include the
optional Compose overlay:

```powershell
docker compose -f docker-compose.yml -f compose.ingestion.yml --profile ingestion up -d db floci
docker compose -f docker-compose.yml -f compose.ingestion.yml --profile ingestion ps
```

If Floci is already running from this Compose setup, you can reuse it; the
`up` command leaves the running services in place. Don’t start a second Floci
instance on port 4566.

Host tools such as the AWS CLI connect through `localhost:4566`. For example,
set local-only credentials in the PowerShell session and list Floci's S3
buckets:

```powershell
$env:AWS_ACCESS_KEY_ID = "test"
$env:AWS_SECRET_ACCESS_KEY = "test"
$env:AWS_DEFAULT_REGION = "ap-southeast-1"
aws --endpoint-url http://localhost:4566 s3api list-buckets
```

Inside Floci-launched Lambda containers, use `http://floci:4566` for AWS API
calls and `db:5432` for PostgreSQL. `localhost` inside a Lambda container points
back to that container. The overlay puts Floci and PostgreSQL on the shared
`petstop-ingestion` network and tells Floci to attach Lambda containers there.
The ingestion handlers, fixture server and resource bootstrap are still
planned, so this starts the network services only.

Backend, from `backend/`. The first time, create `.env` as described in [backend/README.md](backend/README.md#environment-variables).

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
