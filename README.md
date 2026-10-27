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
The fetch handler discovers and parses an AVS registry PDF, stores its manifest
and address batches in S3, and dispatches them to an SQS FIFO queue. The
geocoding Lambda consumes that queue asynchronously; S3 then triggers the
transactional database loader when a complete snapshot is ready.

The fetch function needs `FACILITY_SYNC_BUCKET` and a FIFO `GEOCODE_QUEUE_URL`.
The geocoding function needs `FACILITY_SYNC_BUCKET`, `ONEMAP_REQUESTS_PER_MINUTE`
(defaults to 20), and either `ONEMAP_ACCESS_TOKEN` or `ONEMAP_EMAIL` plus
`ONEMAP_PASSWORD`. Configure these on the Lambda functions; the backend's
Django process does not automatically pass its environment to them. For local
functions, the queue URL must use `http://floci:4566/...`, reachable on the
shared Docker network.

### Run the facility ingestion locally

This local slice uses the live AVS registry pages and OneMap service. It makes
real outbound requests and uses the OneMap credentials from `backend/.env`.
Apply backend migrations first and make sure Floci and PostgreSQL are running.
Then build the Lambda image and provision local resources:

```powershell
docker build --platform linux/amd64 -t petstop-backend:ingestion-local backend
uv run --project backend python scripts/facilities/bootstrap_local.py `
  --endpoint-url http://localhost:4566 `
  --image petstop-backend:ingestion-local
```

The bootstrap refuses non-local endpoints. It creates or updates the local S3
bucket, geocoding and invocation failure queues, five Lambda functions, SQS
event mappings, and S3 `ready/` and `status/` notifications. It preserves the
PostgreSQL volume and existing rows. Re-run it after rebuilding the image.

Start both registry syncs and wait for the SQS geocoder and S3 loader to finish:

```powershell
uv run --project backend python scripts/facilities/integration_local.py `
  --endpoint-url http://localhost:4566 --source both
```

The runner waits up to one hour by default, then reports run status and
insert/update counts from PostgreSQL. OneMap pacing is enforced, so a complete
registry run can take several minutes. You can select one source with
`--source vet` or `--source pet_shop`. The pipeline uses local emulator
resources and writes facilities to the local database; do not use these
commands against AWS.

Run history, recovery, snapshot review, isolated fixture checks and the AWS
handoff are documented in [facility ingestion operations](docs/facility-ingestion-operations.md).

### Check the Floci Lambda network

With `db` and `floci` running on `petstop-ingestion`, deploy and invoke the
small probe Lambda:

```powershell
uv run --project backend python scripts/facilities/probe_floci.py
```

It should print `reachable: true` for both Floci and PostgreSQL. The probe only
uses the local Floci endpoint and test credentials. It creates or updates the
local `petstop-floci-network-probe` function and role, so rerunning the command
reuses them. If either check fails, confirm the Compose network with
`docker network inspect petstop-ingestion` and review Floci's logs before
starting the ingestion pipeline.

To check event delivery too, run:

```powershell
uv run --project backend python scripts/facilities/probe_floci_events.py
```

This provisions a local FIFO queue, test bucket, SQS event-source mapping and
an S3 notification for objects under `ready/`. It sends one queue message and
uploads one ready object, then waits for receipt objects written by the Lambda.
Success prints receipts for both `sqs` and `s3`, each showing Floci and
PostgreSQL as reachable. The probe resources remain in Floci for inspection or
reruns. Receipt objects go under `receipts/`, outside the notification filter.

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
