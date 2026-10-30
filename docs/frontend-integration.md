# Frontend integration handoff

## Standalone frontend UI

The frontend now defaults to `NEXT_PUBLIC_DATA_SOURCE=local`: sample pets, six fictional merchant catalogues, facility search with a live OneMap basemap and sample pins, care records/reminders, browser-persisted cart and simulated orders, plus merchant editing and per-shop storefront pages. No API or Cognito setup is needed to explore these flows. Local data is a single browser workspace for sample information; document files and pet photos remain in tab memory until reload. Listings are fictional and unverified. Set `NEXT_PUBLIC_DATA_SOURCE=api` to use the API/Cognito boundary described below; the public marketplace catalogue and pet profile APIs are implemented, while other feature endpoints remain outstanding. Local mode does not replace API authorization or implement AWS services.

Updated 2026-10-31. Scope: production-oriented frontend, with backend/infrastructure implemented separately. The data source is chosen at build time; API mode never falls back to sample data.

## Configuration

Copy `frontend/.env.example` to `.env.local` for development. Set these public values before a deployment build:

| Variable | Meaning |
| --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | HTTPS API base including `/api/v1/`; localhost HTTP is allowed for development |
| `NEXT_PUBLIC_COGNITO_DOMAIN` | Cognito managed-login domain, including `https://` |
| `NEXT_PUBLIC_COGNITO_ISSUER` | User-pool issuer, e.g. `https://cognito-idp.ap-southeast-1.amazonaws.com/<pool-id>` |
| `NEXT_PUBLIC_COGNITO_CLIENT_ID` | Public SPA client ID, with **no client secret** |
| `NEXT_PUBLIC_COGNITO_REDIRECT_URI` | Exact deployed `/auth/callback/` URL, including trailing slash |
| `NEXT_PUBLIC_COGNITO_LOGOUT_URI` | Exact post-logout URL on the same frontend origin |
| `NEXT_PUBLIC_COGNITO_SCOPES` | Default `openid email profile`; add the API resource-server scopes required by the authorizer |

Register callback/logout URLs and authorization-code/PKCE support in Cognito. Tokens stay in memory; a non-sensitive session-presence flag enables a top-level SSO restore after reload. The token endpoint must support the public browser client. Relevant primary references: [Cognito authorization endpoint](https://docs.aws.amazon.com/cognito/latest/developerguide/authorization-endpoint.html), [token endpoint](https://docs.aws.amazon.com/cognito/latest/developerguide/token-endpoint.html), and [oidc-client-ts settings](https://authts.github.io/oidc-client-ts/interfaces/UserManagerSettings.html).

## Local development sign-in

API mode can be tested offline without Cognito through a development sign-in that works only on a developer's own computer. Setup steps are in `backend/README.md` under "Run pet profiles locally".

- **Frontend:** `NEXT_PUBLIC_DEV_AUTH=true` together with `NEXT_PUBLIC_DATA_SOURCE=api`, in `.env.local`. It is honoured only when the page is served from `localhost` or `127.0.0.1`; on any other hostname, or when the flag is unset, Cognito sign-in behaves exactly as before. Never set it for a deployment build.
- **Backend:** `DJANGO_DEBUG=True` and `DJANGO_DEV_AUTH=true`, outside AWS Lambda (Django refuses to start if the opt-in is set inside Lambda). Django accepts the header only when the request's Host is `localhost`, `127.0.0.1` or `[::1]` and its peer address is loopback, so it does not work through a tunnel or from another machine. In AWS, API Gateway's JWT authorizer rejects it before Django.
- **Sign-in:** `/login/` lists the dev users Alice and Bob (owners) and Mira (a merchant who also owns a pet). Choosing one stores only the handle in `sessionStorage`, so each tab can be signed in as a different user to test owner isolation. The API client then sends `Authorization: Dev <handle>` instead of a Bearer token, and the role comes from `GET me/` `groups`, as in Cognito mode. Django creates the user on first sign-in; `manage.py seed_pets` gives the three users sample pets, records and reminders.
- **Errors:** if the API rejects the sign-in (401), the login page says "The API did not accept the development sign-in. Set DJANGO_DEBUG=True and DJANGO_DEV_AUTH=true in backend/.env, restart Django, and open the site at http://localhost:3000." If the API cannot be reached it says "Cannot reach the API at NEXT_PUBLIC_API_BASE_URL. Is Django running?" Prefer `http://localhost:3000` over `127.0.0.1`: the `PetFiles` bucket CORS rule and the Cognito callback URLs list only localhost.
- **Files:** with no `PET_FILES_BUCKET`, the backend's upload and download URLs point at `http://localhost:8000/api/v1/local-files/<signed-token>/`. The frontend accepts plain-HTTP file URLs only on `localhost`, `127.0.0.1` and `[::1]`.

## Contract status

Routes, ownership rules, pagination and integer-cent conventions follow `repository-structure.md`. The public marketplace catalogue endpoints and the pet profile endpoints (pets, photos, records, documents and reminders) are implemented in Django. The pet contract is [openapi/pets.yaml](openapi/pets.yaml), which wins over the summary below. Facility, cart, checkout, order and merchant-write endpoints remain unimplemented. The catalogue wire shapes below should be checked against the serializers; the remaining wire shapes are **an explicit integration proposal**, derived from the draft data model, not generated backend types. Do not declare the complete application production-ready from frontend checks alone.

All lists return `{count, next, previous, results}`. `next` must remain on the configured API origin and under the configured base path. IDs may be strings or integers. Errors return `{error:{code,message,details}}`, with 401 for unauthenticated requests, 403 for insufficient role, and 404 for another owner’s private record. API redirects are rejected. Request/response field names are snake_case; amounts and stock are nonnegative integers.

### Public resources

- `GET categories/`: each row `{id,name,slug,sort_order}`.
- `GET merchants/` and `GET merchants/{slug}/`: each row `{id,name,slug,description,logo_key}`. `GET merchants/{slug}/products/` returns the active products for that shop.
- `GET products/?q&category&merchant&min_price&max_price&type&species&sort` and `GET products/{id}/`: rows include `{id,name,slug,description,species,size,price_cents,stock,product_type,duration_minutes,category,merchant,image_key,image_url,also_sold_by}`. Category and merchant are nested metadata objects. `image_url` is null until public product-image delivery is configured. Equivalent offers include their own `{id,name,price_cents,stock,merchant}`.
- `GET facilities/`: `{id,facility_type,name,address,postal_code,latitude,longitude,licence_no,phone,website,source,source_url,last_checked_at,verification_status?,is_24_hours?}`. `facility_type` is `vet` or `pet_shop`; coordinates may be numeric strings or null. Only explicit `verification_status:"verified"` with a check date gets the checked badge; omitted/unverified status is labelled honestly. A check date remains visible and does not imply real-time verification. Missing coordinates produce no fabricated pin. Registry filtering/cleaning belongs to the backend.

### Account and pet resources

- `GET me/`: `{id,display_name,email,groups,merchant}`. `groups` must be an array supplied by the authenticated backend; `merchant` is null or `{id,name,slug}`. Membership of `merchant` enables the merchant workspace in the UI; backend permissions remain mandatory.
- `GET/POST pets/` and `GET/PATCH/DELETE pets/{id}/`: `{id,name,species,breed,sex,date_of_birth,microchip_no,allergies,diet_notes,weight_kg,photo_url,photo_version,created_at,updated_at}`. IDs are UUID strings. Species are `dog`, `cat`, `rabbit`, `bird`, `fish` and `other`; sex is `male`, `female` or `unknown`. `date_of_birth`, `microchip_no`, `weight_kg` (a JSON number with at most 2 decimals), `photo_url` and `photo_version` may be null; `breed` and `diet_notes` are `""` when not recorded; `allergies` is an array. POST requires only `name` and `species` and ignores ID, owner and photo fields; PATCH sends only the changed fields. Both return the full pet, which the frontend merges into its state without refetching. DELETE (204) also removes the pet's records, documents, reminders and stored files. The list is read-only; the frontend still loads records with one `GET pets/{id}/records/` per pet.
- `GET/POST pets/{id}/records/` and `GET/PATCH/DELETE pets/{id}/records/{rid}/`: `{id,pet,name,record_type,date,next_due,clinic,notes,created_at,updated_at}`. `pet` comes from the URL and is never writable. `date` cannot be in the future, and `next_due` cannot be before `date` (checked against the merged values on PATCH). Saving a record never creates a reminder: the frontend suggests one for each record with a `next_due` and no matching reminder, in the record table ("Add reminder") and in the reminder picker. Deleting a record keeps its reminders and documents, with `health_record` set to null.
- `GET/POST reminders/` and `GET/PATCH/DELETE reminders/{id}/`: `{id,pet,health_record,title,due_at,done,is_overdue,is_due_soon,created_at,updated_at}`. The list returns all of the user's reminders, including done ones, ordered by `due_at`; `?pet=` and `?done=true|false` narrow it. `is_overdue` and `is_due_soon` (due within 7 days) are computed per request from Singapore calendar dates; the frontend uses them and applies the same rule itself only when they are absent. Creation sends `pet,title,due_at` and optional `health_record` (a record of the same pet); dates selected in the UI are sent at 09:00 Singapore time. PATCH accepts any of `title`, `due_at`, `done` and `health_record`; a reminder cannot move to another pet. DELETE returns 204.
- `GET pets/{id}/documents/` and `GET/PATCH/DELETE pets/{id}/documents/{did}/`: `{id,pet,health_record,title,content_type,size_bytes,status,uploaded_at,created_at,download_url}`. Only `status: "ready"` documents are listed, retrieved or updated; pending uploads are never listed. `download_url` is a private GET URL valid for 5 minutes, and the frontend fetches the detail route for a fresh one before each download. PATCH changes only `title` and `health_record`. DELETE works on pending and ready documents.
- `POST pets/{id}/documents/`: input `{title,filename,content_type,size_bytes,health_record?}`; output `{document:<pending document row>,upload_url,upload_headers}`. The browser PUTs the file directly to `upload_url` with only the `Content-Type` from `upload_headers` and no Authorization header; the URL is signed for that type and the exact size. The frontend must then call `POST pets/{id}/documents/{did}/complete/`, which checks the stored object and returns the ready document; without that call the document never appears. If the PUT or the completion fails, the frontend makes a best-effort `DELETE pets/{id}/documents/{did}/` and reports the error. `filename` is validated and discarded. PDF, JPEG or PNG up to 10 MB is checked in the browser before any request and enforced again by the server.

Pet photos follow the same three steps. `POST pets/{id}/photo-upload/` with `{content_type,size_bytes}` (JPEG or PNG up to 5 MB) returns `{upload_url,upload_headers}`; the browser PUTs the file; `POST pets/{id}/photo-upload/complete/` verifies it and returns the pet with a fresh `photo_url` and a new `photo_version`. A new request replaces any pending photo upload, so a failed upload needs no cleanup call. `DELETE pets/{id}/photo/` removes the photo. The new-pet form uploads the chosen photo after the pet is created, and the edit page (`/pets/edit/?id=`) replaces or removes it.

`photo_url` is a short-lived, owner-authorized GET URL (1 hour) that changes on every response; `photo_version` changes only when a new photo is completed. `lib/api/photo-cache.ts` fetches `photo_url` with no application Authorization header and keeps one blob URL per pet and `photo_version`, so refreshing the pet list or moving between pages neither downloads the photo again nor flashes the placeholder. Sign-out and account changes clear the cache and revoke its blob URLs. Missing or unavailable photos use a neutral species placeholder.

Upload failures: 409 `upload_incomplete` (the object is not stored yet, or a newer photo request replaced this one) and 400 `upload_invalid` (the stored object does not match the declared size or type) are shown as "The upload could not be verified. Please try again." for documents and "The photo could not be verified. Please try again." for photos; 503 `storage_unavailable` is shown as "File storage is unavailable right now. Please try again later." Uploads that are never completed are discarded by the server after an hour, the next time the owner requests an upload.

Validation errors are 400 `invalid` with `details` keyed by field. A field's value is normally a list of messages, but errors inside a list field are an object keyed by item index, such as `{"allergies": {"3": ["Ensure this field has no more than 50 characters."]}}`. `lib/form-error.ts` shows the first message with a field label. A foreign or deleted id in a body, such as `health_record`, gets DRF's `Invalid pk "…" - object does not exist.`, shown as "This item is no longer available. Refresh and try again." A write that collides with a concurrent change returns `details.non_field_errors: ["This item changed. Refresh and try again."]`; the frontend shows that message alone.

### Basket, checkout and orders

`GET cart/` returns:

```json
{"merchants":[{"merchant":{"id":"m1","name":"Shop","slug":"shop"},"items":[{"product":{"id":"p1","name":"Food","merchant":{"id":"m1","name":"Shop","slug":"shop"},"category":{"id":"c1","name":"Food","slug":"food"},"description":"...","price_cents":1200,"stock":10},"quantity":2}]}],"total_cents":2400}
```

- `POST cart/items/`: `{product:<product id>,quantity:1}`; repeated addition increases quantity. `PATCH cart/items/{product_id}/` sends the desired `{quantity}`; DELETE removes the row.
- `POST checkout/`: `{shipping_name,shipping_phone,shipping_address,shipping_postal_code}` with an `Idempotency-Key` header. Server-side authoritative pricing, stock validation, transactions and key handling are required. On success return an order (below); a failed HTTP/network response does not create a local success state. Retries during the same checkout use the same key. After an interrupted connection the UI asks the customer to check history before retrying.
- `GET orders/`, `GET orders/{id}/` and checkout response: `{id,status,created_at,total_cents,shipping_name,shipping_address,shipping_postal_code,merchant_orders:[{id,merchant:{id,name,slug},status,items:[{product:<id>,product_name,unit_price_cents,quantity}]}]}`. Order `status` follows the draft model (`pending_payment`, `paid`, `cancelled`); the payment-success badge appears only for `paid`. Merchant sub-orders are keyed by merchant IDs, not names. Item names/prices are server-side history snapshots. The UI’s basket total is an estimate from returned line items; the saved order total is always the server value. Payment remains simulated.

### Merchant resources

- `GET merchant/products/`: product rows belonging to the authenticated merchant only.
- `PATCH merchant/products/{id}/`: `{price_cents,stock}`; backend validates membership/ownership and values.
- `GET merchant/orders/`: merchant sub-order rows `{id,created_at,merchant:{id,name,slug},subtotal_cents,status,items:[...]}` using the order-item shape above.
- `PATCH merchant/orders/{id}/`: `{status}`. UI transitions are `paid → processing → shipped → delivered`; the backend must reject invalid transitions and access to another merchant’s sub-order.

## Hosting and external services

- API CORS must allow the exact frontend origin, JSON requests, `Authorization` and `Idempotency-Key`. The frontend does not use API cookies or `credentials:include`.
- Serve `out/` behind HTTPS. CloudFront must map trailing-slash routes such as `/auth/callback/` to their static `index.html` while retaining the callback query in the browser. No Next.js runtime, proxy, API routes or server actions are required.
- Configure security response headers at CloudFront (not unsupported `next.config` headers): no-referrer, no-sniff, frame restrictions and a CSP tested against Next’s emitted inline bootstrap scripts and MapLibre workers. Generate script hashes per build when enforcing CSP. MapLibre needs its worker policy and OneMap connectivity; do not grant all origins access to private data.
- The app requests OneMap’s public `Default/{z}/{x}/{y}.png` raster tiles with OneMap/SLA attribution, following [OneMap’s tile documentation](https://www.onemap.gov.sg/docs/maps/). A map-tile outage falls back to a usable list. Facility ingestion, geocoding and licence verification remain backend responsibilities.
- Existing fictional-shop/product data should be seeded by the backend team, not embedded in the frontend. Real payments, appointment booking, commissions and outbound notifications remain out of scope.

## Validation boundary

Frontend checks cover type safety, lint/format, the HTTP boundary, shape adapters, token routing, pagination constraints, checkout request authority, signed-file headers and static export. A local test-only OIDC/API fixture can exercise user journeys without changing Django. Live Cognito integration, backend access isolation, S3 upload lifecycle and hosting policy must be verified with the deployed services before release.

## Historical checks for API integration

- ESLint, Prettier, TypeScript and the normal static production build passed.
- Eleven Node contract tests passed: private/public request headers, expired sessions, bounded/same-origin pagination, HTTP errors, server-authoritative checkout payloads and totals, merchant writes, malformed-money rejection, safe return URLs, signed-file header isolation and merchant-ID grouping.
- A Chrome walkthrough against the test-only fixture passed public browsing, PKCE sign-in, reload/SSO restoration, private pet creation, record/reminder updates, private report upload, multi-merchant checkout, order detail, sign-out, merchant updates and 320/390/768/1280px layouts. OneMap requests were blocked in that test to verify the usable directory fallback without calling the external provider.
- The API-mode export was checked for test fixture URLs/IDs and contained none. In API mode, missing configuration shows unavailable/sign-in states. The current default is the standalone UI described above.

These checks used the installed Windows Node.js runtime through WSL (equivalent project scripts: `yarn lint`, `yarn format:check`, `yarn tsc --noEmit`, `yarn test`, `yarn build`). No live Cognito pool, Django feature API, S3 policy or deployment was validated.

## Standalone UI validation

The static build (all 18 generated pages), ESLint, full frontend Prettier check and all 14 Node behavior/contract tests passed. The build also ran TypeScript checks. A headless Chrome walkthrough of the default local export verified profile creation, care records and suggested reminders, in-tab document selection, persisted multi-merchant cart and checkout, order history, merchant price/stock editing and fulfilment status, facility filtering and selectable schematic pins. It checked 320/390/768/1280px layouts for horizontal overflow and observed no runtime exceptions or API, Cognito or map-tile requests. Browser automation used an ignored local Chrome harness, not an installed cross-platform browser test suite. This validation does not cover a live backend or AWS deployment.

## Implemented location search (PR 2)

`GET /api/v1/locations/search/?q=...` is public, accepts a trimmed 2–120 character query, and returns `{results: [{label, postal_code, latitude, longitude}]}`. Coordinates are JSON numbers within the Singapore map bounds; postal codes are six-digit strings or null. At most 10 deduplicated usable matches from the first OneMap page are returned. Empty results mean no matches; upstream failures are structured 502/503/504 responses, validation is 400, and throttling is 429. The successful response is `no-store`.

`lib/api/location-services.ts` uses the shared API client with `NEXT_PUBLIC_API_BASE_URL`, including when `NEXT_PUBLIC_DATA_SOURCE=local`. It validates response shape and coordinates, sends no user token, and accepts an abort signal. The directory ignores stale searches and device-location callbacks after a place has been selected. Address search centres a marker; the directory then computes distance/radius against loaded facilities, without implying registry verification.

The optional starting token is `ONEMAP_ACCESS_TOKEN`; renewal credentials are `ONEMAP_EMAIL` and `ONEMAP_PASSWORD`; these are never public frontend configuration. Process-local token reuse and a 30/minute per-client cache throttle are implemented. Production networking, secret provisioning and distributed throttling remain PR 3 integration work.

The map UI now uses location-first search. Selecting an address or device location sets the centre; the loaded facility catalogue is filtered by a 1/2/5/10/20 km straight-line radius (default 5) and sorted nearest first. All Singapore removes the radius limit. Unknown coordinates cannot enter a bounded-radius result. Address suggestions are separate from the facility sidebar. Existing `/locations/search/` payloads are unchanged. Backend-driven facility pagination must eventually filter by radius before paginating; frontend radius calculation currently assumes the existing bounded catalogue is loaded in full.
