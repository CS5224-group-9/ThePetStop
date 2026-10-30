# Repository structure

## Standalone frontend UI

The frontend now defaults to `NEXT_PUBLIC_DATA_SOURCE=local`: sample pets, six fictional merchant catalogues, facility search with a live OneMap basemap and sample pins, care records/reminders, browser-persisted cart and simulated orders, plus merchant editing. No API or Cognito setup is needed to explore these flows. Local data is a single browser workspace for sample information; document files and pet photos remain in tab memory until reload. Listings are fictional and unverified. Set `NEXT_PUBLIC_DATA_SOURCE=api` to opt into the previously implemented API/Cognito boundary described below; the marketplace catalogue and pet profile APIs are implemented, while the other feature endpoints remain outstanding. Local mode does not replace API authorization or implement AWS services.

The current layout, the target layout for the MVP, the API contract, and the rules that keep the domains separate. Create a directory when its first real file goes in, not before.

Last updated 2026-10-31.

## Current structure

```text
cs5224-petstop/
├── .github/
│   ├── workflows/
│   │   ├── aws-test.yml       # Manual AWS OIDC connection check
│   │   ├── backend-ci.yml     # Ruff lint and format check, manage.py check
│   │   ├── deploy.yml         # On push to main: cdk deploy, migrate, frontend → S3, CloudFront invalidation
│   │   ├── frontend-ci.yml    # ESLint, Prettier, tests and static build
│   │   └── infra-ci.yml       # Prettier, tsc and CDK template tests
│   └── pull_request_template.md
├── backend/                # Django API (uv); api, accounts, pets, facilities (location search), marketplace (catalogue)
├── docker-compose.yml      # Local PostgreSQL 16 on 127.0.0.1, port PETSTOP_DB_PORT (default 5432)
├── frontend/               # Next.js app (Yarn); standalone UI with optional API mode
├── infra/                  # AWS CDK app (Yarn)
├── docs/                   # Context files (this directory); openapi/ holds the per-domain API contracts
├── .env.example            # PETSTOP_DB_PORT for docker compose
├── AGENTS.md
├── CLAUDE.md
└── README.md
```

## Target structure

```text
cs5224-petstop/
├── .github/
│   ├── workflows/
│   │   ├── aws-test.yml
│   │   ├── backend-ci.yml     # uv sync --locked, ruff, check, makemigrations --check, test
│   │   ├── frontend-ci.yml    # yarn install --frozen-lockfile, lint, format:check, test, build
│   │   ├── deploy.yml         # On push to main: cdk deploy (image → ECR, stacks), migrate, web → S3, CloudFront invalidation
│   │   └── infra-ci.yml       # yarn install --frozen-lockfile, format:check, tsc, template tests
│   └── pull_request_template.md
├── backend/
├── frontend/
├── infra/                     # AWS CDK app in TypeScript (own package.json, Yarn): network, database, auth, storage, API, jobs, monitoring stacks
├── tests/
│   ├── load/                  # k6 scripts
│   └── security/              # Postman collection and environment template (no real tokens)
├── docker-compose.yml         # Local PostgreSQL
└── docs/
```

### Backend

```text
backend/
├── config/
│   ├── settings.py            # One settings module, driven by environment variables
│   ├── dev_auth.py            # When the local-only dev sign-in is enabled (DEBUG, DJANGO_DEV_AUTH, not Lambda)
│   └── urls.py                # admin/ and api/v1/
├── api/                       # Shared code, no models
│   ├── urls.py                # Mounts each app under api/v1/
│   ├── views.py               # GET /health/
│   ├── authentication.py      # Cognito JWT verification → accounts.User; local-only `Authorization: Dev <handle>`
│   ├── permissions.py         # IsMerchant and other shared permission classes
│   ├── pagination.py
│   ├── exceptions.py          # The single error format
│   ├── storage.py             # Private pet files: presigned S3 PUT/GET, HEAD and delete; local signed-URL backend in DEBUG
│   ├── local_files.py         # /api/v1/local-files/<token>/, mounted only with the local storage backend
│   └── log_filters.py         # Redacts local file tokens from logs
├── accounts/                  # User model, GET /me/
├── pets/                      # Feature 2: Pet, HealthRecord, PetDocument, Reminder
│   ├── reminders.py           # Singapore due dates, overdue and due-soon flags
│   ├── uploads.py             # Upload tickets, completion check, presigned download URLs, stale-upload purge
│   ├── tests/
│   └── management/commands/seed_pets.py   # Idempotent local demo pets, records and reminders
├── facilities/                # Feature 1: Facility
│   ├── search.py              # Bounding box and haversine distance on latitude/longitude (no PostGIS)
│   ├── avs.py                 # Fetch and parse AVS registries
│   ├── onemap.py              # Geocode through OneMap
│   ├── fixtures/facilities.json   # Fallback snapshot of the cleaned registry
│   └── management/commands/
│       ├── fetch_facilities.py    # Download AVS + geocode → JSON (runs outside the VPC)
│       └── load_facilities.py     # JSON → upsert Facility rows (runs inside the VPC)
├── marketplace/               # Feature 3: catalogue (D2), cart, checkout and orders (D3), merchant APIs (D1)
│   ├── checkout.py            # Transactional checkout and simulated payment
│   ├── fixtures/catalogue/    # Seed data; see data-model.md
│   └── management/commands/load_catalogue.py
├── Dockerfile                 # Lambda image; handlers in config/lambda_handler.py
├── .env.example
├── manage.py
├── pyproject.toml
└── uv.lock
```

Each feature app has the usual `models.py`, `serializers.py`, `views.py`, `urls.py`, `admin.py`, `migrations/` and a `tests/` package.

Rules:

- `pets`, `facilities` and `marketplace` **do not import from each other**. Each owns its tables. This carries over the report's rule that each domain owns its data.
- Feature apps may import from `api` and `accounts`, and reference users through `settings.AUTH_USER_MODEL`.
- `api` holds no models and no feature logic.
- Views stay thin. Logic that is not about HTTP goes in a named module (`search.py`, `checkout.py`, `reminders.py`), so it can be tested without a request.
- Code that calls an outside service (`avs.py`, `onemap.py`, `storage.py`) stays in its own module so tests can replace it. **Tests never call AWS, AVS or OneMap.**

The root `.gitignore` ignores `**/.env*` but keeps `.env.example`, so commit that file with placeholder values only.

### Frontend

The app is statically exported (decided; see [architecture.md](architecture.md#decisions)), so pages that show one record take the id as a query parameter, and there are no Next.js API routes or server actions. Check the bundled Next.js 16 docs in `frontend/node_modules/next/dist/docs/` before creating routes.

```text
frontend/
├── app/
│   ├── page.tsx               # Dashboard: pets, upcoming reminders, shortcuts
│   ├── login/  signup/
│   ├── pets/                  # List; new; edit?id=; detail?id= (profile, records, documents, reminders)
│   ├── map/                   # Map and directory, facility detail panel
│   ├── shop/                  # Catalogue; product?id=; merchant?slug=
│   ├── cart/
│   ├── checkout/
│   ├── orders/                # History; detail?id=
│   └── merchant/              # Merchant portal: products, orders
├── components/
└── lib/
    ├── api/                   # The one API client, services, and wire adapters written to match docs/openapi/
    │   └── photo-cache.ts     # Downloaded pet photos as blob URLs, keyed by pet and photo_version
    ├── auth/                  # Cognito sign-in and token handling
    │   └── dev.ts             # Local-only dev sign-in (NEXT_PUBLIC_DEV_AUTH; localhost and 127.0.0.1 only)
    ├── reminders.ts           # Overdue and due-soon rule; which records still need a suggested reminder
    ├── pet-input.ts           # Photo, document and allergy input checks
    └── form-error.ts          # Turns API validation errors into one form message
```

The API base URL comes from `NEXT_PUBLIC_API_BASE_URL`. Nothing else calls `fetch` against the API directly.

The frontend implements the listed routes plus `/auth/callback/` and `/pets/reminders/`. Cognito sign-in uses `oidc-client-ts`; MapLibre renders OneMap tiles. `lib/api/` owns requests, adapters and domain operations; `lib/auth/` owns OAuth session handling. Local mode uses fictional sample data and browser storage; API mode uses the configured backend. The pet profile API is implemented and its contract is [openapi/pets.yaml](openapi/pets.yaml); the wire contract for facilities, cart, checkout, orders and merchant writes is still provisional: see [frontend-integration.md](frontend-integration.md). `tests/api.test.mts` checks the HTTP/contract boundary, `tests/local-ui.test.mts` checks local interactions, and `tests/pets-api.test.mts` and `tests/pets-local.test.mts` cover the pet services in both modes. Frontend CI now includes those checks and a static build.

## API contract

All routes are under `/api/v1/`. Each implemented domain has a hand-written OpenAPI contract in `docs/openapi/` (for example [openapi/pets.yaml](openapi/pets.yaml)), and the frontend's wire parsing in `lib/api/adapters.ts` is written to match it.

### Conventions

- JSON in and out; field names in `snake_case`.
- Money is in integer cents; timestamps are ISO 8601 with offset.
- Lists are paginated as `{"count", "next", "previous", "results"}`, 20 items per page by default.
- Every error uses one shape:

  ```json
  {"error": {"code": "out_of_stock", "message": "Only 2 left of Salmon Kibble 2 kg", "details": {}}}
  ```

- A missing or invalid token returns 401. A non-merchant calling a merchant route gets 403. Another user's private record gets **404**.

### Routes

| Route | Methods | Auth | Owner |
| --- | --- | --- | --- |
| `/health/` | GET | Public | A |
| `/me/` | GET | User | A |
| `/pets/` | GET (read-only), POST | User | B |
| `/pets/{id}/` | GET, PATCH, DELETE (also its records, documents, reminders and files) | Pet owner | B |
| `/pets/{id}/photo-upload/` | POST → presigned PUT URL | Pet owner | B |
| `/pets/{id}/photo-upload/complete/` | POST (verify the upload, make it the pet's photo) | Pet owner | B |
| `/pets/{id}/photo/` | DELETE | Pet owner | B |
| `/pets/{id}/records/` | GET, POST | Pet owner | B |
| `/pets/{id}/records/{rid}/` | GET, PATCH, DELETE | Pet owner | B |
| `/pets/{id}/documents/` | GET (ready only, with presigned GET URLs), POST → pending document and presigned PUT URL | Pet owner | B |
| `/pets/{id}/documents/{did}/` | GET, PATCH (title, health record) on ready documents; DELETE (pending or ready) | Pet owner | B |
| `/pets/{id}/documents/{did}/complete/` | POST (verify the upload, mark the document ready) | Pet owner | B |
| `/reminders/?pet&done` | GET (all reminders incl. done, with flags), POST | User | B |
| `/reminders/{id}/` | GET, PATCH (title, due date, done, health record), DELETE | Reminder owner | B |
| `/facilities/?lat&lng&radius_km&type&q&postal_code` | GET | Public | C |
| `/facilities/{id}/` | GET | Public | C |
| `/locations/search/?q=...` | GET | Public | C |
| `/categories/` | GET | Public | D2 |
| `/merchants/`, `/merchants/{slug}/`, `/merchants/{slug}/products/` | GET | Public | D2 |
| `/products/?q&category&merchant&min_price&max_price&type&species&sort` | GET | Public | D2 |
| `/products/{id}/` | GET, including `also_sold_by` | Public | D2 |
| `/cart/` | GET (grouped by merchant), DELETE (empty) | User | D3 |
| `/cart/items/` | POST | User | D3 |
| `/cart/items/{product_id}/` | PATCH (quantity), DELETE | User | D3 |
| `/checkout/` | POST (shipping details) → paid order | User | D3 |
| `/orders/`, `/orders/{id}/` | GET | Order owner | D3 |
| `/merchant/products/` | GET, POST | Merchant | D1 |
| `/merchant/products/{id}/` | PATCH, DELETE | Merchant who owns it | D1 |
| `/merchant/products/{id}/image-upload/` | POST → presigned PUT URL | Merchant who owns it | D1 |
| `/merchant/orders/`, `/merchant/orders/{id}/` | GET, PATCH (status) | Merchant who owns it | D1 |

Agree any change to a route with the frontend owner of that page, and change both sides in the same pull request.

## Working agreements

- `main` is protected. Work on a branch named `<type>/<short-description>`, such as `feat/pets-crud` or `docs/mvp-scope`, and open a pull request with one reviewer.
- Once CI exists, backend and frontend checks must pass before merge. Every model change ships with its migration.
- `marketplace` migrations are written only by D2. D1 and D3 request model changes from D2.
- Merging to `main` deploys to the `dev` stage, so integrate continuously instead of on Sunday.
- Update `docs/` in the same pull request when a decision is made or the built state changes.

The location-search route is implemented independently of facility registry ingestion. Its contract and local setup are in `frontend-integration.md`; production networking remains open in `architecture.md`.
