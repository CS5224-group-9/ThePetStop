# Repository structure

## Standalone frontend UI

The frontend now defaults to `NEXT_PUBLIC_DATA_SOURCE=local`: sample pets, six fictional merchant catalogues, facility search with an offline schematic map, care records/reminders, browser-persisted cart and simulated orders, plus merchant editing. No API or Cognito setup is needed to explore these flows. Local data is a single browser workspace for sample information; document files remain in tab memory until reload. Listings are fictional and unverified. Set `NEXT_PUBLIC_DATA_SOURCE=api` to opt into the previously implemented API/Cognito boundary described below; backend endpoints remain a separate task. Local mode does not replace API authorization or implement AWS services.

The current layout, the target layout for the MVP, the API contract, and the rules that keep the domains separate. Create a directory when its first real file goes in, not before.

Last updated 2026-10-19.

## Current structure

```text
cs5224-petstop/
├── .github/
│   ├── workflows/
│   │   ├── aws-test.yml       # Manual AWS OIDC connection check
│   │   ├── backend-ci.yml     # Ruff lint and format check, manage.py check
│   │   └── frontend-ci.yml    # ESLint, Prettier, tests and static build
│   └── pull_request_template.md
├── backend/                # Django API (uv); api, accounts, and empty feature apps
├── docker-compose.yml      # Local PostgreSQL 16
├── frontend/               # Next.js app (Yarn); standalone UI with optional API mode
├── docs/                   # Context files (this directory)
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
│   │   └── deploy.yml         # On merge to main: image → ECR, migrate, Lambda, web → S3, CloudFront invalidation
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
│   └── urls.py                # admin/ and api/v1/
├── api/                       # Shared code, no models
│   ├── urls.py                # Mounts each app under api/v1/
│   ├── views.py               # GET /health/
│   ├── authentication.py      # Cognito JWT verification → accounts.User
│   ├── permissions.py         # IsMerchant and other shared permission classes
│   ├── pagination.py
│   ├── exceptions.py          # The single error format
│   └── storage.py             # Presigned S3 URL helpers
├── accounts/                  # User model, GET /me/
├── pets/                      # Feature 2: Pet, HealthRecord, PetDocument, Reminder
│   └── reminders.py           # Which reminders are upcoming or overdue
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
├── Dockerfile                 # Lambda image with the Lambda Web Adapter
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
│   ├── pets/                  # List; new; detail?id= (profile, records, documents, reminders)
│   ├── map/                   # Map and directory, facility detail panel
│   ├── shop/                  # Catalogue; product?id=; merchant?slug=
│   ├── cart/
│   ├── checkout/
│   ├── orders/                # History; detail?id=
│   └── merchant/              # Merchant portal: products, orders
├── components/
└── lib/
    ├── api/                   # The one API client; types generated from the OpenAPI schema
    └── auth/                  # Cognito sign-in and token handling
```

The API base URL comes from `NEXT_PUBLIC_API_BASE_URL`. Nothing else calls `fetch` against the API directly.

The frontend implements the listed routes plus `/auth/callback/` and `/pets/reminders/`. Cognito sign-in uses `oidc-client-ts`; MapLibre renders OneMap tiles. `lib/api/` owns requests, adapters and domain operations; `lib/auth/` owns OAuth session handling. Local mode uses fictional sample data and browser storage; API mode uses the configured backend. The feature backend/schema is not implemented yet, so the frontend wire contract is explicitly provisional: see [frontend-integration.md](frontend-integration.md). `tests/api.test.mts` checks the HTTP/contract boundary and `tests/local-ui.test.mts` checks local interactions. Frontend CI now includes those checks and a static build.

## API contract

All routes are under `/api/v1/`. The OpenAPI schema is generated by drf-spectacular at `/api/v1/schema/`, and the frontend types come from it.

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
| `/pets/` | GET, POST | User | B |
| `/pets/{id}/` | GET, PATCH, DELETE | Pet owner | B |
| `/pets/{id}/photo-upload/` | POST → presigned PUT URL | Pet owner | B |
| `/pets/{id}/records/` | GET, POST | Pet owner | B |
| `/pets/{id}/records/{rid}/` | GET, PATCH, DELETE | Pet owner | B |
| `/pets/{id}/documents/` | GET (with presigned GET URLs), POST → presigned PUT URL | Pet owner | B |
| `/pets/{id}/documents/{did}/` | DELETE | Pet owner | B |
| `/reminders/` | GET (upcoming and overdue, all pets), POST | User | B |
| `/reminders/{id}/` | PATCH (done, due date), DELETE | Reminder owner | B |
| `/facilities/?lat&lng&radius_km&type&q&postal_code` | GET | Public | C |
| `/facilities/{id}/` | GET | Public | C |
| `/categories/` | GET | Public | D2 |
| `/merchants/`, `/merchants/{slug}/` | GET | Public | D2 |
| `/products/?q&category&merchant&min_price&max_price&type&sort` | GET | Public | D2 |
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
