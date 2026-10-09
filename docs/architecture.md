# Architecture: proposed and current

The preliminary report proposes an AWS architecture. This repository does not implement it yet. This file records both, and the decisions still open between them.

Current state was checked on 2026-10-07. Re-check the code before relying on the "current" columns.

## Proposed architecture (from the report)

Region: AWS Asia Pacific (Singapore), `ap-southeast-1`.

| Layer | Component | Proposed AWS service |
| --- | --- | --- |
| User channel | Pet owner web frontend | Amazon CloudFront |
| Shared access | Domain routing and edge protection | Amazon Route 53 |
| Shared access | API management and feature routing | Amazon API Gateway |
| Shared access | Identity and access management | Amazon Cognito |
| Pet profiles | Profile service and access rules | AWS Lambda |
| Pet profiles | Profile and file metadata | Amazon RDS for PostgreSQL |
| Pet profiles | Private photos and vet reports | Amazon S3, short-lived presigned URLs |
| Map and directory | Map and Directory Service | AWS Lambda |
| Map and directory | Facility database | Amazon RDS for PostgreSQL (the diagram adds PostGIS) |
| Map and directory | AVS Data Synchronisation Service | AWS Lambda on a schedule (the diagram shows EventBridge) |
| Map and directory | Geocoding | OneMap API |
| Map and directory | Map rendering in the browser | MapLibre |
| Marketplace | Checkout and Payment Service | AWS Lambda, PayNow API |
| Marketplace | Order, Ledger and Invoicing Service | AWS Lambda, Amazon RDS for PostgreSQL, invoices in S3 |
| Marketplace | Ad Placement Service | AWS Lambda, Amazon RDS |
| Marketplace | Reconciliation Job | Scheduled AWS Lambda, settlement reports in S3 |
| Platform | Monitoring and auditing | Amazon CloudWatch, AWS CloudTrail |
| Platform | Secrets | AWS Secrets Manager |
| Platform | Container management | Amazon ECR, Amazon ECS |
| Platform | Deployment | GitHub Actions |

The diagram labels are small in the source PDF; rows marked "the diagram" were read from it and should be confirmed against the original figure.

The diagram also states a collaboration rule: each feature domain owns its services, storage, and data, with no direct database access across domains.

## Current implementation

| Area | What exists |
| --- | --- |
| Frontend | Next.js 16 with React 19, TypeScript, and Tailwind CSS 4 in `frontend/`. Only the default `create-next-app` page. No API client, map library, or test runner installed. |
| Backend | Django 6.1 with Django REST Framework in `backend/`. One app, `api`, with empty models, views, and tests. The only URL is `admin/`. |
| Database | SQLite (`backend/db.sqlite3`, ignored by Git). |
| Authentication | Django's default session auth apps are installed. No Cognito, no token auth, no DRF configuration. |
| File storage | None. |
| External data | None. No AVS import, no OneMap calls. |
| Infrastructure as code | None. |
| CI | `.github/workflows/lint.yml` checks formatting and lint (Prettier and ESLint for the frontend, Ruff for the backend) on pull requests and pushes to `main`. `.github/workflows/aws-test.yml` runs on manual dispatch, assumes an AWS role through GitHub OIDC, and prints the caller identity. Nothing runs build or tests. |

Backend settings that are incomplete in `backend/config/settings.py`:

- `corsheaders` is in `INSTALLED_APPS`, but `CorsMiddleware` is not in `MIDDLEWARE` and no allowed origins are set, so cross-origin requests from the frontend are not yet permitted.
- There is no `REST_FRAMEWORK` setting, so no default authentication or permission classes are declared.
- `python-dotenv` is a dependency but `load_dotenv()` is never called. `SECRET_KEY` is hardcoded and `DEBUG` is `True`.
- `ALLOWED_HOSTS` is empty and `TIME_ZONE` is `UTC` (the product is Singapore-only).

## Differences between the report and the repository

| Topic | Report | Repository | Effect |
| --- | --- | --- | --- |
| Backend compute | One AWS Lambda service per domain | A single Django project | Decided: keep the single Django project, with one app per domain, hosted as one Lambda function. See backend structure and hosting. |
| Frontend | "React frontend" served by CloudFront | Next.js | Whether the app is statically exported or needs a Node server changes how it is hosted. |
| Tests | Jest for frontend and backend | Django's test runner on the backend; no frontend runner | Backend tests are Django tests. Jest (or another runner) still has to be added to the frontend. |
| Database | PostgreSQL, with PostGIS for facilities | SQLite | Radius search must work on SQLite locally or the team moves local development to PostgreSQL. |
| Payment | PayNow API in the design | Nothing | Prototype payment is simulated. |

## Backend structure and hosting

Decided on 2026-10-07:

- **Structure.** The backend stays a single Django project. The report's three feature domains become Django apps inside it instead of separate Lambda services.
- **Hosting.** The whole project is packaged as one container image and runs as a single AWS Lambda function behind Amazon API Gateway, through a web adapter. All three domains share that function. This keeps the report's Lambda and API Gateway design and the Lambda CloudWatch metrics named in the evaluation.

- **Database.** A small Amazon RDS for PostgreSQL instance (`db.t4g.micro` class) for the prototype, shared by all three apps. Aurora Serverless v2 with auto-pause is the production path if the database needs to scale with usage. DynamoDB was considered and rejected: Django's ORM, migrations, admin, and user model need a relational database, and the data is relational.

Per-domain hosting was considered and rejected: every prototype endpoint, including cart and simulated checkout, is a short request that keeps its state in the database, so none needs an always-on server. If cold starts at checkout become a problem, use provisioned concurrency on the same function.

Consequences to plan for:

- A Lambda function inside a VPC has no internet access without a NAT gateway. Code that calls OneMap or other outside services has to account for this.
- Requests are limited to about 6 MB, so photos and veterinary reports upload directly to S3 through presigned URLs.
- The first request after an idle period is slow while Django loads. Expect this in load-test results.
- Migrations run as a deploy step, by invoking the same image with a different command.

The file layout and the rules for what each app may import are in [repository-structure.md](repository-structure.md).

How the report's services map onto the Django apps:

| Report service | Location |
| --- | --- |
| Pet Profile Service and access rules | `pets/views.py`, `api/permissions.py` |
| Secure pet file access (presigned URLs) | `pets/storage.py` |
| Map and Directory Service | `facilities/views.py`, `facilities/search.py` |
| AVS Data Synchronisation Service | `facilities/management/commands/sync_facilities.py` |
| Checkout and Payment Service | `marketplace/checkout.py`, simulated |
| Order, Ledger and Invoicing Service | `Order` and `OrderItem` only; ledger and invoices are out of scope |
| Ad Placement Service, Reconciliation Job | Not built; out of prototype scope |
| Identity and access management | `accounts/` |

## Open decisions

These need a team decision. Do not settle them inside an unrelated change.

1. **Authentication.** Cognito is proposed. If adopted, Django verifies Cognito-issued JWTs and maps them to local users; otherwise Django issues its own sessions or tokens. Ownership checks on pet data are required either way.
2. **Frontend hosting.** Static export to S3 and CloudFront, or a Node-hosted Next.js server.
3. **Facility search.** PostGIS queries, or a plain latitude and longitude bounding box with distance computed in Python or SQL. The second works on SQLite and is adequate for the few thousand facilities in Singapore.
4. **AVS data sync trigger.** The sync is a Django management command. Whether it runs on a schedule in AWS or is run manually for the prototype is open.
