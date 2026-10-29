# Scope of MVP:

Notes:  
\- Project is a Cloud Service running on AWS with a web interface   
\- Project is NOT a mobile application

## Core feature 1 \- Verified facility discovery

Purpose of feature: Help owners discover relevant and trustworthy pet facilities. 

What should the feature include?

## Core feature 2 \- Pet profiles

Purpose of feature: Give owners a central place to organise important pet information. 

What should the feature include?  
●	Multiple pets per user.  
●	Basic profile: name, species, breed, sex, date of birth, microchip number, photo.  
●	Allergies and dietary preferences.  
●	Vaccination and care records (deworming, grooming, check-ups).  
●	Private vet reports (PDF or image) attached to a pet.  
●	Reminders for upcoming care tasks, shown in the app only: on the dashboard and on each pet's page, with overdue ones highlighted. A vaccination's "next due" date suggests a reminder.  
●	Owners see only their own pets, records, files and reminders.

## Core feature 3 \- Multi-merchant marketplace

Purpose of feature: Make it easier to discover and compare pet supplies across participating retailers. Customers can purchase products from multiple participating merchants in a single checkout experience.

What should the feature include?  
●	Product catalogues from participating shops.  
●	Search, category filters and price comparison: where several shops sell the same product, show each shop's price.  
●	One cart holding items from several merchants, grouped by merchant.  
●	Checkout from our site with simulated payment (no real money moves). One order is split into one sub-order per merchant.  
●	Order history in one place, with per-merchant status.  
●	Basic merchant management: merchants edit their products, prices, stock and images, and move their sub-orders through Processing → Shipped → Delivered.

Additional comments:

* Come up with fake catalogues of fake pet shops, add them to the database. Maybe make up 6 different shops, each with about 20 to 30 products, and there should be about 5-6 product categories?   
* Implement a simple order workflow: Users browse products from multiple merchants, add products to a cart, checkout from our website, view their orders in one place.  
* *This is a nice-to-have*: Consider how to list pet services (e.g. Grooming, Health screening) in the marketplace

## Out of scope

Do not build these without an explicit team decision. Log them as future work for the final report.  
●	Real payments (PayNow), tokenisation, refunds: the brief asks for a simulated checkout.  
●	Ledger, commission split, seller payouts, GST invoices, reconciliation.  
●	Advertising and sponsored listings.  
●	Appointment booking for vets or groomers.  
●	Email, SMS and push notifications: reminders are in-app only.  
●	Pet parks and pet-friendly venues on the map: the brief covers vets and pet shops only.  
●	Merchant self-signup and onboarding: the team creates the accounts for the six seeded shops.

## Cloud infrastructure

Should minimally have:

* Secure user authentication and access controls.  
* Managed database for pet profiles, facilities, products and orders.  
* Object storage for product images.  
* Serverless APIs, monitoring, logging and backups.

How we meet them:

| Requirement | Implementation |
| :---- | :---- |
| Authentication and access controls | Cognito sign-up and sign-in, groups owner and merchant. API Gateway rejects missing or invalid tokens on protected routes. Django validates the token again, maps its sub to a local user, filters every private query by owner, and checks merchant group membership for merchant routes. |
| Managed database | One RDS PostgreSQL 16 instance (db.t4g.micro, single-AZ). Each Django app owns its own tables. |
| Object storage | S3 product-images, served through CloudFront. Pet photos and vet reports live in a separate private pet-files bucket, accessed through presigned URLs. |
| Serverless APIs | API Gateway HTTP API and one Lambda running Django. No always-on servers. |
| Monitoring and logging | CloudWatch metrics for Lambda and RDS, a dashboard, email alarms, CloudTrail. Structured JSON logs with 14-day retention; no pet medical data or presigned URLs in logs. |
| Backups | RDS automated backups (7 days), a manual snapshot before the demo, S3 versioning on pet-files, one restore tested in Sprint 2\. |

## **Stack and decisions made**

| Layer | Choice |
| :---- | :---- |
| Frontend | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4, Yarn; statically exported to S3 behind CloudFront |
| Map | MapLibre GL JS with OneMap tiles |
| Backend | One Django 6.1 project with Django REST Framework, managed with uv; deployed as one Lambda (container image in ECR \+ AWS Lambda Web Adapter) |
| Database | PostgreSQL 16: Amazon RDS in AWS, Docker Compose locally, a service container in CI |
| Auth | Amazon Cognito user pool, groups owner and merchant |
| Files | Amazon S3 with presigned URLs |
| Infrastructure as code | AWS CDK in TypeScript, in infra/ |
| CI/CD | GitHub Actions, deploying to AWS through the existing OIDC role |
| Region | ap-southeast-1 (Singapore) |

   
Decisions already made (details in docs/architecture.md):  
●      **One Django project, one Lambda.** One app per domain (pets, facilities, marketplace), plus accounts and a shared api app. Apps do not import each other's models. No per-domain Lambdas and no ECS.  
●      **No PostGIS.** Facilities have plain latitude and longitude columns; radius search uses a bounding-box prefilter, then haversine distance in SQL.  
●      **No NAT gateway.** S3 gateway endpoint (free), Secrets Manager interface endpoint in one AZ, Cognito public keys passed to Django at deploy time. The facility sync is split into a fetch step outside the VPC and a load step inside it.  
●      **Static export frontend.** No server rendering, API routes, server actions or middleware. Pages for one record take a query parameter (/pets/detail?id=…); a CloudFront Function maps clean URLs to index.html.  
●      **Local database:** PostgreSQL 16 in Docker Compose; Django reads DATABASE\_URL from backend/.env. Each member has a private database filled from committed fixtures and seed commands.  
●      **Public routes:** facility search and details, categories, merchants and products. Everything else (pets, reminders, cart, checkout, orders, merchant portal) needs a token.  
●      **Reminders are in-app only:** no SES and no scheduled reminder job.  
●      **Payments are simulated:** a "Pay" step marks the order paid.

# Implementation Plan:

Work Owners:

| Workstream | Owner | Owns |
| :---- | :---- | :---- |
| A. Platform & Auth | Zong Hua | IaC, Cognito, API Gateway, CI/CD, VPC/RDS, CloudWatch, backups, cost alarms |
| B. Pet profiles | Yiwei Luo | Pets CRUD, photos/reports on S3, allergies & diet, vaccination & care records |
| C. Facility map | Raynor | AVS ingestion, OneMap geocoding, facilities API, MapLibre map, directory |
| D1. Marketplace \- merchant | Zikun | Merchant accounts, product write API (create/edit, price, stock), image upload, merchant portal, order status updates |
| D2. Marketplace \- catalogue | Liang yifan | Catalogue schema \+ migrations, seed data (6 shops), catalogue/search/filter API & UI, price comparison, storefront; survey and user testing |
| D3. Marketplace \- orders |  | Cart, checkout (simulated payment), order split per merchant, order history |

## **Phase 0 — Setup (Wed 14 – Sat 17 Oct)**

Goal: by Saturday night anyone can clone the repo, run it locally, merge a PR and see it live on AWS. No feature work starts until M0 is met.

**Wed 14 – Thu 15 Oct: decisions and accounts**

•     	☐ Kickoff: confirm the scope and the out-of-scope list above, fill in the workstream owners; every member installs Docker Desktop (WSL 2 on Windows)  
•     	☐ IaC: **AWS CDK in TypeScript** in infra/ (own package.json and Yarn lockfile). Repo layout: backend/ (Django), frontend/ (Next.js), infra/, tests/load/, tests/security/, docker-compose.yml  
•     	☐ AWS account: IAM Identity Center users per member, MFA on, region ap-southeast-1, **AWS Budgets alarm** (about US\$30/month)  
•     	☐ GitHub: branch protection on main, PR template, issue board with Sprint 1 tickets  
•     	☐ API conventions: REST under /api/v1/, JSON in snake\_case, money in integer cents, pagination {count, next, previous, results}, one error shape {"error": {code, message, details}}; 401 for a missing or invalid token, 403 for a non-merchant on a merchant route, 404 for another user's private record  
•     	☐ Each owner drafts their routes in the API contract (docs/repository-structure.md) and their models in docs/data-model.md; the OpenAPI schema is generated by drf-spectacular, not hand-written  
•     	☐ D2 sends the pet-owner requirements survey (runs in parallel; results by \~25 Oct)

**Fri 16 Oct: infrastructure skeleton**

•     	☐ VPC with private subnets and no NAT gateway: S3 gateway endpoint, Secrets Manager interface endpoint (one AZ)  
•     	☐ RDS PostgreSQL 16 (db.t4g.micro, single-AZ, automated backups on); no PostGIS  
•     	☐ Secrets Manager for DB credentials and the Django secret key  
•     	☐ Cognito user pool \+ app client; groups owner and merchant  
•     	☐ ECR repository and one Lambda "api" running the Django container image with the Lambda Web Adapter, inside the VPC  
•     	☐ API Gateway (HTTP API) with a Cognito JWT authorizer on protected routes; /api/v1/health/ (public) and /api/v1/me/ (authenticated)  
•     	☐ S3 buckets: web (private, behind CloudFront OAC), pet-files (private, presigned URLs), product-images (served via CloudFront), sync (facility data JSON)  
•     	☐ Backend foundation: environment-driven settings, CORS, DRF defaults and error format, TIME\_ZONE Asia/Singapore, accounts.User before the first migration, empty pets, facilities and marketplace apps  
•     	☐ Local database: docker-compose.yml with postgres:16, DATABASE\_URL support (dj-database-url, psycopg), .env.example; README setup steps updated from SQLite to Docker PostgreSQL

**Sat 17 Oct: pipeline and frontend shell — M0**

•     	☐ Next.js shell from the AI-generated template: navigation for the 3 features, static export config (output: 'export', trailingSlash, images.unoptimized), sign-up/sign-in via Cognito (Amplify Auth or equivalent), shared API client using NEXT\_PUBLIC\_API\_BASE\_URL, Jest with one test  
•     	☐ GitHub Actions: backend-ci (uv sync \--locked, manage.py check, makemigrations \--check, Django tests against a Postgres service container) and frontend-ci (yarn install \--immutable, lint, test, build) as required checks on main; deploy on merge (image → ECR, migrate, update Lambda, web → S3, CloudFront invalidation)  
•     	☐ CloudWatch log groups with 14-day retention; one dashboard placeholder  
•     	☐ Spikes so Sprint 1 isn't blocked (C): inspect the AVS registry format; get a OneMap API account and test one geocode; test a MapLibre map with OneMap tiles  
•     	☐ **M0 check:** log in on the deployed site, call /api/v1/me/, see a DB-backed response; a merge to main deploys automatically

## **Sprint 1 \- Vertical Slices (19 Oct \- 25 Oct)**

Goal: Each feature works end to end in its simplest form  
**Platform (A)**  
•     	☐ Shared API client with auth token handling; loading/error states; mobile-responsive layout  
•     	☐ Cognito JWT verification in Django: map the token's sub to accounts.User and read cognito:groups for the merchant role; a test-only authentication class for tests  
•     	☐ Tests gate merges: Django test runner for the backend, Jest for the frontend, one real test per app  
**Pet profiles (B)**  
•     	☐ Pet model \+ CRUD API (/api/v1/pets/); every query filtered by request.user, another owner's pet returns 404  
•     	☐ Pet list and create/edit pages; multiple pets per user  
•     	☐ Profile photo upload via presigned PUT to pet-files, display via presigned GET  
**Facility map (C)**  
•     	☐ Ingestion run once by hand: manage.py fetch\_facilities (AVS vet centres \+ pet shops → parse → validate → geocode with OneMap, postal code first → JSON), then manage.py load\_facilities (JSON → Facility rows with source, licence\_no, last\_checked\_at). Geocoding failures go into a report, never silently dropped  
•     	☐ Commit the cleaned snapshot as facilities/fixtures/facilities.json, so local development, tests and a first deploy work without AVS or OneMap  
•     	☐ GET /api/v1/facilities/?lat\&lng\&radius\_km\&type\&q\&postal\_code using a bounding-box prefilter and haversine distance (no PostGIS)  
•     	☐ MapLibre map centred on Singapore with markers \+ a list view; type filter (vet / pet shop)  
**Marketplace (D1, D2, D3)**  
•     	☐ Models: Merchant, Category, ProductGroup (links equivalent products across shops for price comparison), Product. D2 writes all marketplace migrations; D1 reviews  
•     	☐ Seed data: **6 fictional shops × 20–30 products × 6 categories** (Food, Treats, Health & Hygiene, Toys, Accessories, Grooming Supplies), with 30–40 shared product groups so comparison has real matches. JSON in backend/marketplace/fixtures/catalogue/ (D2: categories, product groups, shops 1–3; D3: shops 4–6), loaded by the idempotent manage.py load\_catalogue  
•     	☐ Product images to product-images, generated or royalty-free placeholders (D3)  
•     	☐ Catalogue API: list, search, filter by category/merchant/price, product detail (D2)  
•     	☐ Catalogue and product detail pages (D2)  
•     	☐ CartItem, Order, MerchantOrder and OrderItem models (through D2's migrations) \+ cart API (D3)  
•     	☐ Merchant accounts: the team links each seeded merchant to a Cognito login in the merchant group; merchants land in the portal after login (D1)  
•     	☐ Merchant product API: create, edit, delete, only for the merchant's own products (D1)  
•     	☐ Portal page listing the merchant's products (D1)  
**Sprint 1 End Goal:** a new user signs up, adds a pet with a photo, finds the nearest vet on the map, and browses products from all 6 shops.

## **Sprint 2 \- Feature-complete core (26 Oct \- 1 Nov)**

Goal: Every item in MVP brief is developed  
**Platform (A)**  
•     	☐ EventBridge Scheduler for the weekly facility fetch (C), plus an S3 event on the new JSON in sync that starts the load, so the load never runs before the file exists  
•     	☐ Merchant access control: an IsMerchant permission from the Cognito merchant group, so D1's portal isn't blocked  
•     	☐ Checkout DB support for D3: connection reuse (CONN\_MAX\_AGE), transaction handling, migration review; cap reserved concurrency, and add RDS Proxy only if load tests show connection exhaustion  
•     	☐ Monitoring and logging: structured JSON logs from Django (no pet medical data or presigned URLs), CloudWatch dashboard (Lambda errors, duration, throttles, concurrency; RDS CPU, memory, connections; API 4xx/5xx), alarms to email, CloudTrail on  
•     	☐ Backups: confirm RDS automated backups (7 days), S3 versioning on pet-files, test one restore  
•     	☐ Write the Postman security collection (tests/security/) and k6 scripts (tests/load/) against Sprint 1 endpoints, ready to run in Sprint 3  
**Pet profiles (B)**  
•     	☐ Allergies and dietary preferences on the profile  
•     	☐ Vaccination records (vaccine, date given, next due, clinic) and care records (deworming, grooming, check-ups)  
•     	☐ Vet report upload (PDF, JPEG or PNG, up to 10 MB) linked to a pet, via presigned PUT to pet-files  
•     	☐ Reminders, in-app only: user sets due dates (auto-suggested from a vaccination's "next due"); GET /api/v1/reminders/ flags upcoming and overdue when called; dashboard widget and overdue badge on each pet's page  
**Facility map (C)**  
•     	☐ Facility detail panel: address, phone, email/website, licence number, **verification source \+ last-checked date**  
•     	☐ "Get directions" deep link (Google Maps / OneMap) from the user's location  
•     	☐ Searchable directory (by name, postal code, area) alongside the map  
•     	☐ Weekly sync: fetch\_facilities runs on schedule outside the VPC and writes JSON to the sync bucket; load\_facilities runs inside the VPC, updates last\_checked\_at and marks removed facilities inactive  
**Marketplace (D1, D2, D3)**  
•     	☐ Price comparison on product detail: "also sold by" with each merchant's price; public shop storefront page (D2)  
•     	☐ Search and filter polish: sorting, empty states (D2)  
•     	☐ Cart (persisted server-side per user) holding items from several merchants, grouped by merchant (D3)  
•     	☐ Checkout: address form → order summary → **simulated payment** → one Order split into one MerchantOrder per merchant; label the payment step clearly as simulated (D3)  
•     	☐ In one DB transaction: lock the products (select\_for\_update), reject inactive or out-of-stock items with a clear error, copy product names and prices into order items, decrement stock, clear the cart (D3)  
•     	☐ Order history and order detail pages with per-merchant status (D3)  
•     	☐ Product image upload via presigned URL to product-images; price and stock editing (D1)  
•     	☐ Product group picker in the product editor, so new products appear in price comparison (D1)  
•     	☐ Portal order list of the merchant's own merchant orders, built against seeded orders (D1)

**Sprint 2 End Goal:** run the four usability tasks from the report end to end. Book 5–6 pet owners for user testing on 3–5 Nov.

## **Sprint 3 \- Merchant tools, hardening, testing (2 Nov \- 8 Nov)**

Goal: code freeze Sunday night with the cloud requirements met and all four evaluation streams done.

**Features**  
•     	☐ Basic merchant management (D1): merchants edit their products, stock and prices, upload images, and update merchant order status (Processing → Shipped → Delivered), shown in D3's order history  
•     	☐ Pet services listing (D1), only if M2 was met: products with type "service" and a duration in a "Pet Services" category, bought through the same checkout; no booking  
•     	☐ Reminders polish: edit, mark done, overdue state (B); checkout polish (D3)  
•     	☐ UX fixes from user testing (all)  
**Cloud requirements (A)**  
•     	☐ Access control audit across all endpoints: owners only see their pets, records, files, reminders and orders; merchants only their products and merchant orders; S3 buckets block public access  
•     	☐ Fix what the load and security tests find; tune Lambda memory and reserved concurrency  
•     	☐ Optional: AWS WAF managed rules on CloudFront  
**Evaluation**  
•     	☐ Usability testing Tue 3 – Thu 5 Nov (D2): 4 tasks, record time, errors, confusion points  
•     	☐ Integration tests (C): frontend ↔ API ↔ DB for pets, facility search and the marketplace  
•     	☐ Run the Postman security collection (A): requests with no valid token are rejected; user A gets 404 for user B's pet or order  
•     	☐ Run the k6 load test (A): e.g. 50 virtual users for 5 minutes on facility search and catalogue; capture p95 latency and error rate alongside CloudWatch metrics (expect slow cold starts)  
•     	☐ Collate survey results for the report (D2)

## **Final stretch (Mon 9 – Wed 11 Nov)**

Goal (M4): a stable demo and a submitted report; no new features.

•     	☐ **Mon 9 Nov:** fix P1 bugs; reset demo data (fresh seed, 2–3 demo users with pets, records and past orders, demo merchant logins for the 6 shops); take a manual RDS snapshot  
•     	☐ **Mon 9 – Tue 10 Nov:** final report sections — architecture as built (update the diagram: one Django Lambda, no PostGIS, no NAT gateway, in-app reminders), evaluation results, AWS cost actuals vs an on-premises estimate (hardware, maintenance, electricity, ops staff), future work (PayNow, commission and payouts, ads, booking, email/SMS/push notifications, pet parks, merchant self-signup)  
•     	☐ **Tue 10 Nov:** full demo rehearsal on the deployed site; record a backup demo video in case of live issues  
•     	☐ **Wed 11 Nov:** submit; tag the release in GitHub

After submission, scale RDS down or stop it to avoid idle charges.

