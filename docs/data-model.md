# Data model

Django marketplace catalogue and pets models are implemented; the remaining domain models are drafts. This file is the source of truth for models; the MVP Development Plan lists only model names and points here. Coordinate marketplace schema changes with D1 and D3, and update this file when a model changes.

Each app's tables share one PostgreSQL schema with the app name as prefix (`pets_pet`, `marketplace_product`), which keeps the domains separate without custom schema routing.

Owners: `accounts` A, `pets` B, `facilities` C, `marketplace` D2 for migrations and the catalogue, D3 for cart and orders, D1 for merchant writes. Agree models by **Fri 16 Oct** and refine them in Sprint 1.

Last updated 2026-10-31.

## Conventions

- **Money** is an integer number of Singapore cents (`price_cents`, `total_cents`). Never use floats. The API returns cents and the frontend formats them as S$.
- **Times** are stored in UTC (`USE_TZ = True`) and shown in Singapore time.
- **Files** are stored as S3 object keys (`photo_key`, `file_key`, `image_key`), never as URLs. The API turns keys into presigned or CloudFront URLs when it responds.
- **Ownership.** Every private model reaches a user through a foreign key, so querysets can be filtered by `request.user`.
- **Lists of short values**, such as allergies, use `JSONField(default=list)`, so tests do not depend on PostgreSQL-only fields.
- Apps reference the user through `settings.AUTH_USER_MODEL`, and do not import each other's models.

## accounts

| Model | Fields | Notes |
| --- | --- | --- |
| `User` (extends `AbstractUser`) | `cognito_sub` (unique), `email`, `display_name` | Created or updated on first authenticated request. Merchant role comes from the token's `cognito:groups`, not a column. |

## pets (Feature 2)

Implemented in `backend/pets/models.py`; the wire shapes are in [openapi/pets.yaml](openapi/pets.yaml). All four models use UUID primary keys (`id`), because ids appear in page URLs such as `/pets/detail/?id=…`. Text columns are never nullable: an absent value is stored as `""`, and the API returns `null` where the contract marks the field nullable. Child models reach the owner through `pet` → `owner`.

| Model | Fields | Notes |
| --- | --- | --- |
| `Pet` | `owner` → User, `name` (≤ 50), `species` (dog, cat, rabbit, bird, fish, other), `breed` (≤ 80, default `""`), `sex` (male, female, unknown; default unknown), `date_of_birth` (nullable), `microchip_no` (`""` or exactly 15 digits; the API returns `""` as null), `allergies` (list of strings), `diet_notes` (≤ 500), `weight_kg` (decimal with 2 places, nullable), `photo_key`, `photo_content_type`, `pending_photo_key`, `pending_photo_content_type`, `pending_photo_size_bytes` (nullable), `pending_photo_requested_at` (nullable), `created_at`, `updated_at` | Multiple pets per user, of any role (merchants may own pets). Ordered by `created_at`, then `id`. Checks: `microchip_no` is `""` or 15 digits; `weight_kg` is null or above 0 (the API accepts 0.01 to 500). Index on (`owner`, `created_at`). The photo and pending-photo fields are never serialized; the API returns `photo_url` and `photo_version` instead. Deleting a pet deletes its records, documents and reminders. |
| `HealthRecord` | `pet` → Pet, `record_type` (vaccination, deworming, grooming, checkup, other), `name` (≤ 100, for example "DHPPiL"), `date`, `next_due` (nullable), `clinic` (≤ 100, free text, not a link to `facilities`), `notes` (≤ 1000, enforced by the serializer), `created_at`, `updated_at` | Vaccination and care records. Ordered by `date` descending, then newest first. Check: `next_due` is null or on or after `date`. Index on (`pet`, `-date`). Deleting a record keeps its documents and reminders, with `health_record` set to null. |
| `PetDocument` | `pet` → Pet, `health_record` → HealthRecord (nullable), `title` (≤ 150), `file_key` (unique), `content_type` (application/pdf, image/jpeg, image/png), `size_bytes`, `status` (pending, ready; default pending), `uploaded_at` (nullable; set when the upload is completed), `created_at` | Private vet reports: PDF, JPEG or PNG, up to 10 MiB (check: 1 ≤ `size_bytes` ≤ 10485760). Only `ready` rows are listed, retrieved or updated. There is no file-name column. Ordered by `uploaded_at` descending, then newest first. Index on (`pet`, `status`). |
| `Reminder` | `pet` → Pet, `health_record` → HealthRecord (nullable), `title` (≤ 150), `due_at`, `done` (default false), `created_at`, `updated_at` | Shown in the app only. Ordered by `due_at`, then `created_at`, then `id`. Index on (`pet`, `due_at`). `is_overdue` and `is_due_soon` are computed per request in `pets/reminders.py`, never stored. |

### Reminders

Reminders are never created automatically: there are no signals or `save()` overrides, and saving a record with `next_due` creates nothing. The UI suggests a reminder for each record that has a `next_due` and no matching reminder, and the owner creates it with `POST /reminders/`, linked through `health_record`. Due dates are compared as Asia/Singapore calendar dates. An open reminder is overdue when its due date is before today, and due soon when it falls between today and today + 7 days inclusive; a done reminder is neither. Dates picked in the UI are sent as 09:00 Singapore time.

### File lifecycle

Pet photos and vet reports live in the private `PetFiles` bucket. In local development with `DJANGO_DEBUG=True` and no `PET_FILES_BUCKET`, they live under `backend/.local-storage/` instead (gitignored and dockerignored). With neither, file operations return 503 `storage_unavailable`. `api/storage.py` is the only code that touches storage.

- **Keys** are `pets/{pet_id}/documents/{document_id}.{ext}` and `pets/{pet_id}/photos/{uuid}.{ext}`, with a new random UUID for every photo upload. Keys contain no names, titles or file names; the `filename` a client sends is validated and discarded.
- **Uploads** take three steps. The API returns a presigned PUT URL, valid for 15 minutes and signed for the exact Content-Type and Content-Length. The browser PUTs the file directly to storage. The client then calls the matching `complete` route, which checks the stored object's size and type. A match marks the document `ready` and sets `uploaded_at`, or moves the pending photo into `photo_key`. A missing object returns 409 and keeps the upload pending. A mismatch deletes the pending document or photo and its object (400 `upload_invalid`). Photos are JPEG or PNG up to 5 MiB; documents are PDF, JPEG or PNG up to 10 MiB.
- **Downloads** use presigned GET URLs created on each response: 5 minutes for documents (as an attachment with a generic file name) and 1 hour for photos, both with `Cache-Control: private, no-store`. Pending files are never exposed.
- **`photo_version`** is the UUID in the photo key (null when there is no photo). It changes only when a new photo is completed, so the frontend caches the downloaded photo by it while `photo_url` changes on every response.
- **Deletes** of a document, a photo or a pet remove the stored objects after the transaction commits. This is best effort: a storage failure is logged by exception class only and does not fail the request. Replacing a photo deletes the old object in the same way.
- **Abandoned uploads.** Whenever an owner requests a new photo or document upload, that owner's pending documents and pending photos older than 1 hour are purged: the rows or pending fields are cleared, and the objects are deleted after commit. `GET /pets/` is read-only and never purges.
- **Old versions.** `PetFiles` is versioned. A lifecycle rule expires noncurrent versions after 7 days, removes expired delete markers and aborts incomplete multipart uploads after 1 day, so a deleted vet report is gone within about a week.

Known gaps: deleting a `User` deletes its pets in bulk without deleting their files, and deletes made in the Django admin do not clean up files either. Neither happens through the API. Also, a presigned PUT cannot be revoked: if the same pet's photo upload is requested twice within 15 minutes (two tabs), the first, replaced upload can still land after the server deleted its key. That object stays in the private bucket, unreferenced, even after the pet is deleted.

`manage.py seed_pets` creates fictional demo pets, records and reminders for the local dev users (alice, bob and mira) or for a named existing user. It is idempotent, resets only the rows it seeded, creates no files, and refuses to run in AWS Lambda.

## facilities (Feature 1)

| Model | Fields | Notes |
| --- | --- | --- |
| `Facility` | `facility_type` (vet, pet_shop), `name`, `licence_no`, `address`, `postal_code`, `latitude`, `longitude`, `phone`, `email`, `website`, `source` (for example "AVS registry of licensed pet shops"), `source_url`, `last_checked_at`, `active` | `latitude` and `longitude` are plain decimal fields; there is no PostGIS geometry column. Unique on (`facility_type`, `licence_no`). Index on (`latitude`, `longitude`) and on `postal_code`. Inactive rows stay for history but are never returned. |

## marketplace (Feature 3)

| Model | Fields | Notes |
| --- | --- | --- |
| `Merchant` | `name`, `slug`, `description`, `logo_key`, `owner` → User (nullable) | The six seeded shops. `owner` is the merchant login. |
| `Category` | `name`, `slug`, `sort_order` | Six seeded categories |
| `ProductGroup` | `canonical_name` | Links the same product sold by different shops, for price comparison |
| `Product` | `merchant` → Merchant, `category` → Category, `group` → ProductGroup (nullable), `name`, `description`, `price_cents`, `stock`, `image_key`, `product_type` (product, service), `duration_minutes` (nullable, services only), `active`, `created_at`, `updated_at` | Merchants edit their own products only |
| `CartItem` | `user` → User, `product` → Product, `quantity` | Unique on (`user`, `product`). The cart is the set of a user's items, grouped by merchant when read. |
| `Order` | `user` → User, `status` (pending_payment, paid, cancelled), `total_cents`, shipping name, phone, address and postal code, `payment_ref` (simulated, for example `SIM-…`), `paid_at`, `created_at` | One per checkout |
| `MerchantOrder` | `order` → Order, `merchant` → Merchant, `subtotal_cents`, `status` (paid, processing, shipped, delivered, cancelled), `updated_at` | One per merchant in an order. Merchants see and update only their own. |
| `OrderItem` | `merchant_order` → MerchantOrder, `product` → Product (protected), `product_name`, `unit_price_cents`, `quantity` | Name and price are copied at checkout, so later edits do not change history |

### Checkout rules

Checkout runs in one database transaction:

1. Lock the user's cart items' products (`select_for_update`).
2. Reject the checkout with a clear error if any product is inactive or out of stock.
3. Create the `Order`, then one `MerchantOrder` per merchant, then the `OrderItem`s with copied names and prices.
4. Decrement stock and clear the cart.
5. Run the simulated payment step. It sets `payment_ref`, `paid_at` and status `paid`, and sets each `MerchantOrder` to `paid`.

Nothing in the UI may suggest a real charge happened. Label the step as a simulated payment.

## Seed catalogue

Required by the MVP brief: fictional shops only, no real brands or businesses presented as participating.

- **6 merchants**, each with **20–30 products**.
- **6 categories**: Food, Treats, Health & Hygiene, Toys, Accessories, Grooming Supplies.
- **30–40 product groups** shared by two or more shops at different prices, so "also sold by" shows real comparisons.
- Product names may be generic, such as "Grain-free salmon dry cat food, 2 kg". Avoid real trademarks.

D2 and D3 split the seed work. D2 has committed three fictional shops with 24 products each (72 rows) and 24 shared product groups; D3 adds shops 4 through 6 and can add further groups to reach the final target of 30 to 40. D2 owns the shared files and the catalogue migrations. File layout, so the two do not edit the same file:

```text
backend/marketplace/fixtures/catalogue/
├── categories.json
├── product_groups.json
├── merchants/
│   ├── shop-1.json   # D2: shops 1–3
│   ├── …
│   └── shop-6.json   # D3: shops 4–6
└── images/           # D3: one image per product, generated or royalty-free, named <merchant-slug>/<product-slug>.jpg
```

`manage.py load_catalogue` is idempotent. It upserts categories, groups, merchants and products, and uploads images to the `product-images` bucket, or serves them locally in development.

If pet services are built, they are `Product` rows with `product_type = "service"` and a `duration_minutes`, in an extra "Pet Services" category, bought through the same checkout.
