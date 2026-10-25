# Roadmap

Milestones and workstreams from the MVP Development Plan, mapped onto this repository. The full plan, with per-sprint checklists, is the team's live plan: <https://claude.ai/code/artifact/d518d744-3763-4feb-bba7-50de560b0b85>.

Last updated 2026-10-25.

## Milestones

Every milestone ends with a working deployment on AWS, not just local code.

| Milestone | Date | Done when |
| --- | --- | --- |
| **M0** Walking skeleton | Sat 17 Oct | A user signs in on the deployed site, and the frontend calls `/api/v1/me/` and gets a database-backed answer. Merging to `main` deploys automatically. |
| **M1** Vertical slices | Sun 25 Oct | Pets CRUD, facilities on the map, and the product catalogue all work on real or seeded data. A merchant can edit their own products. |
| **M2** Core feature-complete | Sun 1 Nov | Every item in the MVP brief works except basic merchant management: records and reminders, facility details and directions, cart, checkout and order history. |
| **M3** Code freeze | Sun 8 Nov | Merchant management is done, the cloud requirements are met, and all evaluation streams are done. Only bug fixes after this. |
| **M4** Submission | Wed 11 Nov | Demo rehearsed, backup video recorded, final report submitted, release tagged. |

Sprints: setup Wed 14 – Sat 17 Oct, Sprint 1 Mon 19 – Sun 25 Oct, Sprint 2 Mon 26 Oct – Sun 1 Nov, Sprint 3 Mon 2 – Sun 8 Nov.

## Workstreams

Six people, six workstreams. Each owner builds their feature front to back: Django app, API and their own Next.js pages. The frontend starts from an AI-generated template, so there is no separate app-shell workstream. The marketplace is split by user: D1 builds what merchants manage, D2 what buyers browse, and D3 cart, checkout and orders.

| Workstream | Person | Owns in this repository | Sprint 3 extra |
| --- | --- | --- | --- |
| **A** Platform and auth | TBD | `infra/`, `.github/workflows/`, `backend/config/`, `backend/api/` (shared API code, auth, permissions, storage helpers), `backend/accounts/`, `Dockerfile`, the frontend's shared API client and Cognito sign-in (`frontend/lib/`), monitoring, backups, cost alarms, `tests/load/`, `tests/security/` | Load and security testing |
| **B** Pet profiles | TBD | `backend/pets/` (pets, health records, vet reports, in-app reminders), `frontend/app/pets/`, the dashboard reminders widget | Reminders polish |
| **C** Facility map | TBD | `backend/facilities/` (AVS ingestion, OneMap geocoding, search API, weekly sync), `frontend/app/map/` | Integration tests for all three domains |
| **D1** Marketplace: merchant | TBD | Merchant accounts, `/merchant/*` APIs (product create, edit and delete, price, stock, image upload, product group picker, order status updates), `frontend/app/merchant/` | Pet services listing, if M2 is met |
| **D2** Marketplace: catalogue | TBD | **All `marketplace` migrations** and the catalogue models, seed shops 1–3, catalogue, search, filter and price-comparison APIs, `frontend/app/shop/` (catalogue, product detail, storefront); the survey and usability testing | Usability testing sessions |
| **D3** Marketplace: orders | TBD | Cart and order models (through D2's migrations), seed shops 4–6, product images, cart, checkout with simulated payment, per-merchant order split, `frontend/app/cart/`, `checkout/`, `orders/` | Checkout polish |

`marketplace` is one Django app shared by D1, D2 and D3, so D2 owns its migrations. D1 and D3 ask D2 for model changes rather than adding migrations themselves, which avoids clashing migration files.

Working rhythm: a 15-minute daily standup (async in chat is fine), sprint planning on Monday, and a demo and retro on Sunday. Every pull request needs one reviewer, and `main` deploys automatically to the `dev` stage.

## Before Sprint 1 starts (M0)

Mostly workstream A, with input from everyone:

1. Kickoff: confirm the scope cuts and fill in the Person column above. Every member installs Docker Desktop (WSL 2 on Windows) for the local database; see [architecture.md](architecture.md#decisions).
2. AWS account: IAM Identity Center user and MFA for each member, region `ap-southeast-1`, and an AWS Budgets alarm (about US$30 a month).
3. GitHub: PR template, and an issue board with Sprint 1 tickets.
4. Backend foundation:
   - environment-driven settings, CORS, DRF defaults and the error format;
   - `accounts.User`;
   - empty `pets`, `facilities` and `marketplace` apps;
   - `/health/` and `/me/`;
   - `docker-compose.yml` with `postgres:16`, and `DATABASE_URL` support in settings (`dj-database-url`, `psycopg`);
   - `.env.example`;
   - README setup steps updated from SQLite to Docker PostgreSQL.
5. Frontend foundation:
   - the AI-generated template committed to `frontend/`, with navigation for the three features;
   - static export config;
   - the shared API client, and sign-up and sign-in wired to Cognito;
   - Jest with one test.
6. CI workflows, required as status checks on `main`, plus the deploy workflow.
7. CDK stacks in TypeScript for VPC (S3 gateway and Secrets Manager endpoints, no NAT gateway), RDS, Secrets Manager, Cognito, ECR and Lambda, API Gateway, S3 and CloudFront, and log retention.
8. Each owner drafts their slice of the API contract in [repository-structure.md](repository-structure.md#api-contract) and their models in [data-model.md](data-model.md).
9. Spikes and parallel work:
   - C inspects the AVS registry format, gets a OneMap account and tests one geocode, and tests a MapLibre map with OneMap tiles;
   - D2 drafts the catalogue models and reviews them with D1, and plans the seed catalogue with D3 (format in [data-model.md](data-model.md#seed-catalogue));
   - D2 sends the pet-owner requirements survey, with results by about 25 Oct.

## D2 status as of 25 Oct 2026

- Implemented the marketplace catalogue schema and initial migration, including the cart/order tables D3 builds on.
- Added an idempotent `load_catalogue` command and fictional seed data for D2 shops 1 through 3 (24 products each, six categories, 24 cross-shop comparison groups). D3 still needs to add shops 4 through 6.
- Added public catalogue, search/filter, merchant storefront and product comparison API routes. The frontend supports catalogue browsing, category/species/merchant/price filters, sorting, product details, offer comparisons and merchant storefronts in standalone UI mode.
- Drafted the pet-owner requirements survey and summarized the supplied 64-row simulated dataset in [pet-owner-requirements-survey.md](pet-owner-requirements-survey.md). There are no real respondent results; report the figures as simulated only.
- Prepared the moderator script, task cards and observation sheet in [usability-test-plan.md](usability-test-plan.md); recruiting participants and running sessions remain future work for 3?5 Nov.

## Demo checks

- **Sun 25 Oct (M1):** a new user signs up, adds a pet with a photo, finds the nearest vet on the map, and browses products from all six shops. A merchant logs in and edits one of their products.
- **Sun 1 Nov (M2):** the four usability tasks run end to end. D2 books five or six pet owners for user testing on 3–5 Nov.
- **Sun 8 Nov (M3):** code freeze. Usability, integration, security and load tests are done.
- **Mon 9 – Wed 11 Nov:** P1 fixes, demo data reset (two or three demo users with pets, records and past orders), RDS snapshot, report, rehearsal, backup video, submission and release tag. Stop or scale down RDS after submission.
