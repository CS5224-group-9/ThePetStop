# Product context

Summary of the Group 9 preliminary report (CS5224). The report itself is not checked into this repository. It states prototype goals and a proposed design; see [architecture.md](architecture.md) for what is actually built.

## What ThePetStop is

An integrated web app (SaaS on AWS) for pet owners in Singapore, covering multiple pet species. It combines three things that existing local services only offer separately: a pet health record, a map of pet facilities, and a marketplace.

Users:

- Pet owners in Singapore (primary users; the platform is free for them).
- Pet-related businesses such as pet shops and clinics (the paying side in the long-term business model).

## Prototype scope

The prototype demonstrates core user value in three features.

### 1. Pet profiles

- Authenticated users create, view, and update multiple pet profiles.
- Each profile holds name, species, breed, and a profile photo.
- Vaccination information is recorded per pet (the "digital pet passport"). Singapore requires owners to keep microchip and vaccination records.
- Users upload private veterinary reports and attach them to the correct pet.
- Owners can access only their own pets. Photos and reports are private files.

### 2. Facility map and directory

- Users find AVS-licensed pet shops and veterinary clinics near a location.
- The frontend sends location, search radius, and category; the backend returns nearby active facilities.
- Each facility shows name, address, contact information, facility type, and AVS licence status.
- Results appear as map markers and as a directory list.
- Facility data comes from the AVS public registries, geocoded from address to latitude and longitude through the OneMap API.

### 3. Marketplace

- Users browse pet products stored in a database, add them to a cart, and complete a **simulated** payment.
- No real money moves in the prototype.

## Outside the prototype

The report describes these as long-term plans or does not carry them into the prototype scope. Do not build them without a specific task.

| Item | Status in the report |
| --- | --- |
| Advertising (sponsored map and directory listings) | Explicitly not in the prototype |
| Commission collection (5–10% per transaction) and seller payouts | Explicitly not in the prototype |
| Real PayNow payments, payment tokenisation | Described in the architecture; the prototype uses simulated payment |
| Ledger, refunds, GST-compliant PDF invoices | Described in the architecture; not listed in the prototype scope |
| Reconciliation job against settlement reports | Described in the architecture; not listed in the prototype scope |
| In-app booking of veterinary and grooming services | Mentioned in the motivation only |
| SMS and email notifications for appointments | Mentioned in the motivation only |
| Pet parks and pet-friendly venues on the map | Mentioned in the motivation; the feature section covers AVS-licensed pet shops and clinics only |

## What the evaluation plan requires of the code

The report commits to these checks, so the prototype has to support them.

- **Usability tasks** that must work end to end: create a pet profile and add vaccination information; find and filter a nearby facility; find a product and add it to the cart; complete a simulated purchase.
- **Security checks** (run with Postman): a protected endpoint rejects a request without a valid login token; a logged-in user cannot view another user's pet profile.
- **Functional tests**: unit tests on critical frontend components and backend functions, and integration tests across frontend, backend, and database, focused on pet profiles, facility search, and the marketplace.
- **Load test**: k6 simulating concurrent users against the backend API, recording response times and error rates.
- **Monitoring**: Amazon CloudWatch metrics for the deployed compute and database.
- **Cost comparison** (final report): the AWS deployment against an equivalent on-premises setup.

## Points the report leaves unclear

- The motivation promises booking and notifications, but neither appears in the feature descriptions or the prototype scope.
- The marketplace architecture describes PayNow payments, "tokenised card data", ledgers, and invoices, while the business section says payment is simulated. Simulated payment is the prototype behaviour.
- The report says the scope of the final version is subject to change. Confirm scope with the team before starting anything in the table above.
