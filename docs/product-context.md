# Product context

What the MVP must deliver, what is deliberately left out, and what the evaluation needs from the code. Sources, in order of authority:

1. The **MVP scope brief** (team project doc "Scope of MVP"). It defines the three core features and the cloud requirements.
2. The **MVP Development Plan** (team project doc, live version at <https://claude.ai/code/artifact/d518d744-3763-4feb-bba7-50de560b0b85>). It sets milestones, workstreams and scope cuts.
3. The **Group 9 preliminary report**. It gives the business case and the evaluation plan. Where it describes more than the brief (PayNow, ads, booking, SMS), the brief wins.

Neither source is checked into the repository. For what is actually built, read the code and [architecture.md](architecture.md).

Last updated 2026-10-15.

## What ThePetStop is

A web app hosted on AWS for pet owners in Singapore, covering multiple species. It combines three things local apps only offer separately: a digital pet record, a verified map of pet facilities, and a multi-merchant marketplace for pet supplies.

Users:

- **Pet owners** (primary users; free for them).
- **Merchants**: staff of participating pet shops who manage their catalogue and orders.

## MVP scope

### Feature 1: Verified facility discovery

Purpose: help owners find relevant, trustworthy pet facilities.

- Interactive Singapore map and a searchable directory.
- Filters for veterinary centres and pet shops.
- Facility details: name, address, phone, email or website, licence number.
- Navigation: a "Get directions" link from the user's location (Google Maps or OneMap).
- **Verification source and last-checked date** on every facility.
- Data comes from the AVS public registries of licensed pet shops and veterinary centres, geocoded through the OneMap API.
- Never present stale or made-up facility data as official registry data.

### Feature 2: Pet profiles

Purpose: one place for an owner's important pet information.

- Multiple pets per user.
- Basic profile: name, species, breed, sex, date of birth, microchip number, photo.
- Allergies and dietary preferences.
- Vaccination records and care records: deworming, grooming, check-ups.
- Private vet reports (PDF or image) attached to a pet.
- **Reminders for upcoming care tasks**, shown in the app: on the dashboard and on each pet's page, with overdue ones highlighted. A vaccination's "next due" date suggests a reminder.
- Owners see only their own pets, records, files and reminders.

### Feature 3: Multi-merchant marketplace

Purpose: discover and compare pet supplies across participating retailers, and buy from several merchants in one checkout.

- Product catalogues from participating shops.
- Search, category filters and **price comparison**: where several shops sell the same product, show each shop's price.
- One cart holding items from several merchants, grouped by merchant.
- Checkout from our site with **simulated payment**: no real money moves. One order is split into one sub-order per merchant.
- Order history in one place, with per-merchant status.
- Basic merchant management: merchants edit their products, prices, stock and images, and move their sub-orders through Processing → Shipped → Delivered.

Seed data, required by the brief: **6 fictional shops**, each with **20–30 products**, across **6 categories**. Shops overlap on enough products for price comparison to be visible. See [data-model.md](data-model.md#seed-catalogue).

Nice-to-have, only if milestone M2 is met on time: list pet services, such as grooming or a health screening, in the marketplace and buy them through the same checkout. This is a listing only, with no booking calendar.

### Cloud requirements (from the brief)

- Secure user authentication and access controls.
- Managed database for pet profiles, facilities, products and orders.
- Object storage for product images.
- Serverless APIs, monitoring, logging and backups.

How each is met is in [architecture.md](architecture.md).

## Out of scope

Do not build these without an explicit team decision. Log ideas as future work for the final report.

| Item | Why it is out |
| --- | --- |
| Real payments (PayNow), tokenisation, refunds | The brief asks for a simulated checkout |
| Ledger, commission split, seller payouts, GST invoices, reconciliation | Revenue features; the report keeps them out of the prototype |
| Advertising and sponsored listings | Revenue feature; out of the prototype |
| Appointment booking for vets or groomers | Not in the brief |
| Email, SMS and push notifications | Not in the brief; reminders are shown in the app only |
| Pet parks and pet-friendly venues on the map | The brief covers vets and pet shops only |
| Merchant self-signup and onboarding | Merchant accounts are created by the team for the six seeded shops |

## What the evaluation needs from the code

The report commits to four evaluation streams, so the code has to support them.

- **User requirements survey** with local pet owners. This has no code impact.
- **Usability testing.** These four tasks must work end to end on the deployed site:
  1. Create a pet profile and add a vaccination record.
  2. Find and filter a nearby facility.
  3. Find a product in the marketplace and add it to the cart.
  4. Complete a simulated purchase.
- **Functional and integration testing.**
  - Unit tests on critical backend logic (Django test runner) and frontend components (Jest).
  - Integration tests across frontend, API and database for pets, facility search and the marketplace.
- **Cloud performance and security testing.**
  - A k6 load test against the API, with response times and error rates, read alongside CloudWatch metrics (Lambda duration, errors, throttles, concurrency; RDS CPU, memory, connections).
  - A Postman collection that shows:
    - a protected endpoint rejects a request with no valid token;
    - user A cannot read user B's pet or order.
- **Cost comparison** for the final report: AWS actual costs against an equivalent on-premises setup.

## Timeline

Submission is **Wed 11 Nov 2026**. Milestones and owners are in [roadmap.md](roadmap.md).
