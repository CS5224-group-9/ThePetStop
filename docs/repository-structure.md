# Repository structure

A draft target layout for the prototype, derived from the three features in [product-context.md](product-context.md). Nothing under "Draft target structure" exists yet unless it also appears under "Current structure". Create a directory when the first real file goes into it, not before.

## Current structure

```text
cs5224-petstop/
├── .github/workflows/
│   ├── aws-test.yml        # Manual AWS OIDC connection check
│   └── lint.yml            # Format and lint checks for both projects
├── .vscode/                # Shared format-on-save settings and extensions
├── backend/                # Django API (uv, Ruff)
│   ├── api/                # Empty app: models, views, tests are stubs
│   ├── config/             # Settings, URLs, ASGI, WSGI
│   ├── manage.py
│   ├── pyproject.toml
│   └── uv.lock
├── frontend/               # Next.js app (Yarn, Prettier, ESLint)
│   ├── app/                # layout.tsx, page.tsx, globals.css
│   ├── public/
│   ├── package.json
│   └── yarn.lock
├── docs/                   # Context files (this directory)
├── .editorconfig
├── .gitattributes          # LF line endings
├── AGENTS.md
├── CLAUDE.md
└── README.md
```

## Draft target structure

```text
cs5224-petstop/
├── .github/workflows/
│   ├── aws-test.yml
│   ├── lint.yml
│   ├── backend-ci.yml      # uv sync, manage.py check, manage.py test
│   ├── frontend-ci.yml     # yarn lint, yarn build, frontend tests
│   └── deploy.yml          # Deployment through the OIDC role
├── backend/
│   ├── config/             # Settings, root URLconf
│   ├── accounts/           # User identity, auth integration
│   ├── pets/               # Feature 1: pet profiles
│   ├── facilities/         # Feature 2: map and directory
│   ├── marketplace/        # Feature 3: products, cart, simulated checkout
│   ├── api/                # Shared API code: versioned URL routing, health check
│   └── Dockerfile          # Container image used for deployment
├── frontend/
│   ├── app/
│   │   ├── (auth)/         # Sign in, sign up
│   │   ├── pets/           # Pet list, pet detail, vaccinations, documents
│   │   ├── map/            # Facility map and directory
│   │   ├── marketplace/    # Product list and product detail
│   │   ├── cart/
│   │   └── checkout/       # Simulated payment and confirmation
│   ├── components/         # Shared UI components
│   └── lib/
│       └── api/            # Typed client for the Django API
├── infra/                  # Infrastructure as code for the AWS deployment
├── tests/
│   └── load/               # k6 scripts for the evaluation
└── docs/
```

### Backend file layout

The backend is a single Django project with one app per feature domain (decided on 2026-10-07; see [architecture.md](architecture.md)). It is deployed as one container image running on AWS Lambda.

Only `config/`, `api/`, `manage.py`, `pyproject.toml`, and `uv.lock` exist today. Add a file when a task needs it.

```text
backend/
├── config/                         # Project configuration
│   ├── settings.py                 # One settings module, driven by environment variables
│   ├── urls.py                     # admin/ and api/v1/
│   ├── asgi.py
│   └── wsgi.py
├── api/                            # Shared API code, no models
│   ├── urls.py                     # Mounts each app's urls under api/v1/
│   ├── views.py                    # Health check
│   ├── permissions.py              # IsOwner and other shared permission classes
│   ├── pagination.py
│   ├── exceptions.py               # One error response format for every endpoint
│   └── tests/
├── accounts/                       # Who the user is
│   ├── models.py                   # User model or profile, per the authentication decision
│   ├── authentication.py           # Token verification, if Cognito is adopted
│   ├── serializers.py
│   ├── views.py                    # Current user endpoint
│   ├── urls.py
│   └── tests/
├── pets/                           # Feature 1: pet profiles
│   ├── migrations/
│   ├── models.py                   # Pet, VaccinationRecord, VetDocument
│   ├── serializers.py
│   ├── views.py                    # Querysets filtered to request.user
│   ├── urls.py
│   ├── storage.py                  # Presigned upload and download URLs for private files
│   ├── admin.py
│   └── tests/
│       ├── test_api.py
│       └── test_ownership.py       # Unauthenticated and cross-user access are refused
├── facilities/                     # Feature 2: map and directory
│   ├── migrations/
│   ├── models.py                   # Facility
│   ├── serializers.py
│   ├── views.py                    # Search by lat, lng, radius, category
│   ├── urls.py
│   ├── search.py                   # Distance and radius filtering
│   ├── avs.py                      # Fetch and parse the AVS registries
│   ├── onemap.py                   # Geocode an address through the OneMap API
│   ├── management/commands/
│   │   └── sync_facilities.py      # Runs avs.py and onemap.py, upserts Facility rows
│   ├── fixtures/                   # Small sample data set for local development and tests
│   ├── admin.py
│   └── tests/
├── marketplace/                    # Feature 3: products, cart, simulated checkout
│   ├── migrations/
│   ├── models.py                   # Product, Cart, CartItem, Order, OrderItem
│   ├── serializers.py
│   ├── views.py
│   ├── urls.py
│   ├── checkout.py                 # Order totals and the simulated payment step
│   ├── fixtures/                   # Sample products
│   ├── admin.py
│   └── tests/
├── Dockerfile                      # Container image used for deployment
├── .dockerignore
├── .env.example                    # Names of required variables, no real values
├── manage.py
├── pyproject.toml
└── uv.lock
```

Rules that keep the apps separable:

- `pets`, `facilities`, and `marketplace` do not import from each other. This carries over the report's rule that each domain owns its data.
- A feature app may import from `api` (shared helpers) and may reference the user through `settings.AUTH_USER_MODEL`.
- `api` holds no models and no feature logic. It only wires URLs and shared behaviour.
- Views stay thin. Logic that is not about HTTP goes in a named module beside them (`search.py`, `checkout.py`, `storage.py`), so it can be tested without a request.
- Code that calls an outside service (`avs.py`, `onemap.py`, `storage.py`) is kept in its own module so tests can replace it. Tests must not call AVS, OneMap, or AWS.
- Each app's tests live in a `tests/` package once `tests.py` grows past one concern.

One existing setting conflicts with this layout: the root `.gitignore` pattern `**/.env*` also ignores `.env.example`. Add an exception for it when that file is created.

### Backend apps

| App | Owns | Draft models |
| --- | --- | --- |
| `accounts` | Who the user is | Depends on the authentication decision in [architecture.md](architecture.md) |
| `pets` | Pet profiles and health records | `Pet`, `VaccinationRecord`, `VetDocument` |
| `facilities` | AVS-licensed pet shops and clinics | `Facility` (name, address, contact, type, licence status, latitude, longitude, last synced) |
| `marketplace` | Products and simulated orders | `Product`, `Cart`, `CartItem`, `Order`, `OrderItem` |

The AVS import and OneMap geocoding run from a management command in `facilities/management/commands/`, which can later be triggered by a scheduler.

### Draft API routes

Paths are a starting point for keeping the frontend and backend consistent. Agree them before building against them.

| Prefix | Purpose | Auth |
| --- | --- | --- |
| `/api/v1/pets/` | List and create the current user's pets | Required, owner only |
| `/api/v1/pets/{id}/` | Retrieve and update one pet | Required, owner only |
| `/api/v1/pets/{id}/vaccinations/` | Vaccination records for a pet | Required, owner only |
| `/api/v1/pets/{id}/documents/` | Private veterinary reports for a pet | Required, owner only |
| `/api/v1/facilities/` | Search by `lat`, `lng`, `radius`, `category` | To be decided |
| `/api/v1/facilities/{id}/` | Facility details | To be decided |
| `/api/v1/products/` | Browse products | To be decided |
| `/api/v1/cart/` | The current user's cart | Required |
| `/api/v1/orders/` | Simulated checkout and order history | Required, owner only |

A request for another user's pet, document, or order should return `404`, so the response does not confirm that the record exists.

### Frontend routes

The route names above are a draft. `frontend/AGENTS.md` requires reading the bundled Next.js documentation in `node_modules/next/dist/docs/` before writing code, because this Next.js version differs from older conventions. Check the route group and dynamic segment conventions there before creating these directories.

## Suggested order of work

1. Backend settings: environment loading, CORS, DRF defaults, and the authentication decision.
2. CI workflows for backend and frontend, so later work is checked automatically.
3. `pets`, with ownership tests, since it carries the security checks named in the evaluation.
4. `facilities`, starting from a small set of imported records.
5. `marketplace`, ending with simulated checkout.
6. `infra/`, deployment, and `tests/load/`.
