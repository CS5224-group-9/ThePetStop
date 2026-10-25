# Data model

Django marketplace catalogue models are implemented; the remaining domain models are drafts. This file is the source of truth for models; the MVP Development Plan lists only model names and points here. Coordinate marketplace schema changes with D1 and D3, and update this file when a model changes.

Each app's tables share one PostgreSQL schema with the app name as prefix (`pets_pet`, `marketplace_product`), which keeps the domains separate without custom schema routing.

Owners: `accounts` A, `pets` B, `facilities` C, `marketplace` D2 for migrations and the catalogue, D3 for cart and orders, D1 for merchant writes. Agree models by **Fri 16 Oct** and refine them in Sprint 1.

Last updated 2026-10-25.

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

| Model | Fields | Notes |
| --- | --- | --- |
| `Pet` | `owner` → User, `name`, `species` (dog, cat, rabbit, bird, other), `breed`, `sex` (male, female, unknown), `date_of_birth` (nullable), `microchip_no` (nullable), `photo_key` (nullable), `allergies` (list of strings), `diet_notes`, `created_at`, `updated_at` | Multiple pets per user |
| `HealthRecord` | `pet` → Pet, `record_type` (vaccination, deworming, grooming, checkup, other), `name` (for example "DHPPiL"), `date`, `next_due` (nullable), `clinic`, `notes`, `created_at` | Vaccination and care records |
| `PetDocument` | `pet` → Pet, `health_record` → HealthRecord (nullable), `title`, `file_key`, `content_type`, `size_bytes`, `uploaded_at` | Private vet reports: PDF, JPEG or PNG, up to 10 MB |
| `Reminder` | `pet` → Pet, `health_record` → HealthRecord (nullable), `title`, `due_at`, `done` | Suggested when a health record has `next_due`. Shown in the app only. |

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
