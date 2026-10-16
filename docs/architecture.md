# Architecture

The target AWS architecture for the MVP, what is built today, and the decisions still open. Scope is in [product-context.md](product-context.md); file layout and API routes are in [repository-structure.md](repository-structure.md).

Last updated 2026-10-15. Re-check the code before trusting the "Current state" section.

## Stack

| Layer | Choice |
| --- | --- |
| Frontend | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4, Yarn; statically exported |
| Map | MapLibre GL JS with OneMap tiles |
| Backend | One Django 6.1 project with Django REST Framework, managed with uv |
| Database | PostgreSQL 16: Amazon RDS in AWS, Docker Compose locally, a service container in CI |
| Auth | Amazon Cognito user pool, groups `owner` and `merchant` |
| Files | Amazon S3 with presigned URLs |
| Infrastructure as code | AWS CDK in TypeScript |
| CI/CD | GitHub Actions, deploying to AWS through the existing OIDC role |
| Region | `ap-southeast-1` (Singapore) |

### Relation to the MVP Development Plan

The plan matches this stack and the decisions below (updated 2026-10-16). It lists only model names and defers to [data-model.md](data-model.md) for fields, and API routes are drafted in the [API contract](repository-structure.md#api-contract) rather than as hand-written OpenAPI stubs. If the plan and this file disagree again, record the difference here.

## AWS architecture

```text
Browser
  │
  ├── CloudFront ── S3 "web"              Next.js static export
  │       └────── S3 "product-images"     public catalogue images
  │
  └── API Gateway (HTTP API) ── Cognito JWT authorizer on protected routes
          │
          └── Lambda "api"  (Django container image + Lambda Web Adapter, in VPC)
                 ├── RDS PostgreSQL       private subnets
                 ├── Secrets Manager      DB credentials, Django secret key
                 └── S3 "pet-files"       private: pet photos, vet reports (presigned URLs)

EventBridge Scheduler, weekly (facility sync, Sprint 2)
  └── Lambda "fetch" (same image, outside the VPC) → AVS + OneMap → JSON in S3 "sync"
        └── S3 event on the new JSON
              └── Lambda "jobs" (same image, in the VPC) → manage.py load_facilities → RDS

CloudWatch Logs + dashboard + alarms · CloudTrail · AWS Budgets · RDS automated backups
```

### How the brief's cloud requirements are met

| Requirement | Implementation |
| --- | --- |
| Secure authentication and access controls | Cognito sign-up and sign-in. API Gateway rejects missing or invalid tokens on protected routes. Django maps the token's `sub` to a local user, filters every private query by owner, and checks `merchant` group membership for merchant routes. |
| Managed database | One RDS PostgreSQL instance (`db.t4g.micro`, single-AZ). Each Django app owns its own tables. |
| Object storage for product images | S3 `product-images`, served through CloudFront. Pet photos and vet reports live in a separate private bucket. |
| Serverless APIs | API Gateway HTTP API and Lambda. There are no always-on servers. |
| Monitoring | CloudWatch metrics for Lambda and RDS, a dashboard, email alarms on errors and throttles, and CloudTrail for the account. |
| Logging | Structured JSON logs from Django to CloudWatch Logs, with 14-day retention. No pet medical data or presigned URLs in logs. |
| Backups | RDS automated backups (7 days), a manual snapshot before the demo, and S3 versioning on `pet-files`. One restore is tested in Sprint 2. |

### Django on Lambda

- The backend is packaged as one container image in Amazon ECR. The **AWS Lambda Web Adapter** runs gunicorn inside Lambda, so Django runs unchanged.
- Migrations and the facility sync use the same image with a different command, invoked as a deploy step, by EventBridge Scheduler (fetch) or by an S3 event (load).
- Requests are capped at about 6 MB, so files upload **directly to S3** through presigned PUT URLs and never pass through Django.
- The first request after an idle period is slow while Django starts. Expect this in load-test results; use provisioned concurrency only if checkout latency becomes a problem.
- Concurrent Lambdas each open a database connection. Use `CONN_MAX_AGE`, cap reserved concurrency, and add RDS Proxy only if load tests show connection exhaustion.

### Authentication flow

1. The frontend signs users up and in against Cognito (Amplify Auth or an equivalent library) and keeps the ID or access token.
2. The API client sends `Authorization: Bearer <token>`.
3. API Gateway's JWT authorizer validates the token on protected routes. Public routes, such as browsing facilities and products, have no authorizer.
4. Django validates the token again with Cognito's public keys, which are passed to it as configuration at deploy time because the Lambda has no internet access. It creates or updates the local `accounts.User` keyed by `sub`, and reads `cognito:groups` for the merchant role.
5. Local development uses the same flow against the dev user pool. Tests use a test-only authentication class.

Requests for another user's pet, record, file, reminder or order return **404**, not 403, so the response does not reveal that the record exists.

### Facility data

The sync runs in two steps, because the Lambda that can reach RDS has no internet access (see the outbound-access decision under [Decisions](#decisions)):

1. `manage.py fetch_facilities` runs **outside the VPC**. It downloads the AVS registries of licensed pet shops and veterinary centres, parses and validates them, and geocodes each address through OneMap, by postal code first. It writes the result as JSON, to S3 in AWS or to a file locally.
2. `manage.py load_facilities` runs **inside the VPC**. It reads that JSON, through the free S3 gateway endpoint, and upserts `Facility` rows. Each row stores the source, licence number and `last_checked_at`; facilities missing from the registry are marked inactive.

Sprint 1 runs both steps once by hand. From Sprint 2, EventBridge Scheduler runs the fetch weekly, and an S3 event on the new JSON in `sync` starts the load, so the load never runs before the file exists. Geocoding failures go into a report for manual fixing; they are never silently dropped.

A cleaned snapshot is committed as `facilities/fixtures/facilities.json`, so local development, tests and a first deploy work without calling AVS or OneMap. If the AVS format turns out awkward, this snapshot is the fallback and the weekly sync becomes a stretch goal.

### Reminders

- Reminders are in-app only. No email, SMS or push notifications are sent, so there is no SES and no scheduled job.
- `GET /reminders/` returns the user's reminders ordered by due date, with overdue and due-soon flags computed when the request is made.
- The dashboard shows upcoming and overdue reminders; each pet's page shows that pet's.

## Current state

Checked 2026-10-15 on `main`.

| Area | What exists |
| --- | --- |
| Frontend | The default `create-next-app` page. No API client, auth, map library or test runner. |
| Backend | Django project `config/` and one empty app `api/`. The only URL is `admin/`. |
| Database | SQLite (`backend/db.sqlite3`, ignored by Git), until `docker-compose.yml` and the PostgreSQL settings land. |
| Auth | Django's default session auth only. No Cognito integration and no DRF settings. |
| Files, external data | None. |
| Infrastructure as code | None. |
| CI | `.github/workflows/aws-test.yml`: a manually triggered OIDC check that prints the AWS caller identity. Nothing runs lint, build or tests. |

Backend settings to fix in `backend/config/settings.py` before feature work:

- `SECRET_KEY` is hardcoded and the repository is public. Treat that key as leaked: read a new one from the environment.
- `DEBUG = True` and `ALLOWED_HOSTS = []` are hardcoded. Read both from the environment.
- `python-dotenv` is installed but `load_dotenv()` is never called.
- `corsheaders` is installed, but `CorsMiddleware` is not in `MIDDLEWARE` and no allowed origins are set.
- There is no `REST_FRAMEWORK` setting: no default authentication, permission, pagination or exception handler.
- `TIME_ZONE` is `UTC`. Use `Asia/Singapore`; Django still stores UTC.
- There is no custom user model. Add `accounts.User` **before the first real migration**, because changing `AUTH_USER_MODEL` later is very hard.

## Decisions

### Made

| Decision | Choice | Reason |
| --- | --- | --- |
| Backend shape | One Django project, one app per domain, one Lambda function | Every endpoint is a short request with state in the database. One deployable keeps it simple for a six-person team. |
| Database | RDS PostgreSQL `db.t4g.micro` | Django's ORM, migrations and admin need a relational database, and the data is relational. DynamoDB was rejected. |
| Auth | Cognito with `owner` and `merchant` groups | Named in the report and the plan. It is managed and has a free tier. |
| Payments | Simulated: a "Pay" step marks the order paid | MVP brief |
| Reminder channels | In-app only | The brief asks only for reminders. Email (in the MVP plan) and SMS are out of scope. |
| Containers | No ECS. ECR only stores the Lambda image. | MVP plan |
| Frontend hosting (2026-10-15) | Static export (`output: 'export'`) to S3 `web` behind CloudFront | Cheapest and simplest; matches the report. All data comes from the Django API, so no Next.js server features are needed. Consequences: no request-time server rendering, no API routes, server actions or middleware, and pages for one record take a query parameter (`/pets/detail?id=…`). Set `trailingSlash: true` and `images.unoptimized: true`, and add a CloudFront Function that maps a clean URL such as `/pets/detail/` to `/pets/detail/index.html`, because S3 behind CloudFront OAC does not serve sub-folder index files on its own. |
| Facility radius search (2026-10-15) | Plain `latitude` and `longitude` columns: a bounding-box prefilter, then exact (haversine) distance in SQL. No PostGIS. | Singapore has only a few hundred licensed facilities. Avoids GeoDjango's GDAL and GEOS libraries on Windows laptops and in the Lambda image. Differs from the plan. |
| Outbound access from the VPC (2026-10-15) | No NAT gateway. S3 gateway endpoint (free); Secrets Manager interface endpoint in one AZ (roughly US$10 a month; confirm in the AWS Pricing Calculator); Cognito public keys passed to Django at deploy time; facility sync split into a fetch step outside the VPC and a load step inside it (see [Facility data](#facility-data)) | A NAT gateway costs about US$45 a month plus data charges in Singapore. This keeps the weekly sync without one. |
| CDK language (2026-10-15) | TypeScript, in `infra/` with its own `package.json` and Yarn lockfile | Most CDK examples and constructs are TypeScript-first. Only workstream A writes infrastructure code. |
| Local database (2026-10-16) | PostgreSQL 16 in Docker Compose (`docker-compose.yml` at the repo root, `postgres:16` image, a named volume for data). Django reads `DATABASE_URL` from `backend/.env` through `dj-database-url` and `psycopg`. CI uses the same image as a service container. | Local, CI and RDS run the same engine and version, so checkout transactions and row locks behave alike. Each member has a private database filled from committed fixtures and seed commands, never a shared one. Fallback for a laptop where Docker Desktop will not run: a native PostgreSQL 16 install with the same `DATABASE_URL`. If port 5432 is taken, map the container to 5433. |
| Catalogue access (2026-10-15) | Public: facility search and details, categories, merchants and products need no login. Everything else (pets, reminders, cart, checkout, orders, the merchant portal) requires a token. | Users can explore before signing up; smoother usability testing and load tests. |

### Open

None. Add new open decisions here, each with a recommendation, and move them to "Made" once the team settles them.
