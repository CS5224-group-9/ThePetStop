# Frontend integration handoff

## Standalone frontend UI

The frontend now defaults to `NEXT_PUBLIC_DATA_SOURCE=local`: sample pets, six fictional merchant catalogues, facility search with an offline schematic map, care records/reminders, browser-persisted cart and simulated orders, plus merchant editing and per-shop storefront pages. No API or Cognito setup is needed to explore these flows. Local data is a single browser workspace for sample information; document files remain in tab memory until reload. Listings are fictional and unverified. Set `NEXT_PUBLIC_DATA_SOURCE=api` to use the API/Cognito boundary described below; the public marketplace catalogue API is implemented, while other feature endpoints remain outstanding. Local mode does not replace API authorization or implement AWS services.


Updated 2026-10-19. Scope: production-oriented frontend, with backend/infrastructure implemented separately. No Django or AWS resources are created by this change. The app has no runtime demo mode or fallback data.

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

## Contract status

Routes, ownership rules, pagination and integer-cent conventions follow `repository-structure.md`. The public marketplace catalogue endpoints are now implemented in Django. Pet, facility, cart, checkout, order and merchant-write endpoints remain unimplemented. The catalogue wire shapes below should be checked against the serializers; the remaining wire shapes are **an explicit integration proposal**, derived from the draft data model, not generated backend types. Do not declare the complete application production-ready from frontend checks alone.

All lists return `{count, next, previous, results}`. `next` must remain on the configured API origin and under the configured base path. IDs may be strings or integers. Errors return `{error:{code,message,details}}`, with 401 for unauthenticated requests, 403 for insufficient role, and 404 for another owner’s private record. API redirects are rejected. Request/response field names are snake_case; amounts and stock are nonnegative integers.

### Public resources

- `GET categories/`: each row `{id,name,slug,sort_order}`.
- `GET merchants/` and `GET merchants/{slug}/`: each row `{id,name,slug,description,logo_key}`. `GET merchants/{slug}/products/` returns the active products for that shop.
- `GET products/?q&category&merchant&min_price&max_price&type&species&sort` and `GET products/{id}/`: rows include `{id,name,slug,description,species,size,price_cents,stock,product_type,duration_minutes,category,merchant,image_key,image_url,also_sold_by}`. Category and merchant are nested metadata objects. `image_url` is null until public product-image delivery is configured. Equivalent offers include their own `{id,name,price_cents,stock,merchant}`.
- `GET facilities/`: `{id,facility_type,name,address,postal_code,latitude,longitude,licence_no,phone,website,source,source_url,last_checked_at,verification_status?,is_24_hours?}`. `facility_type` is `vet` or `pet_shop`; coordinates may be numeric strings or null. Only explicit `verification_status:"verified"` with a check date gets the checked badge; omitted/unverified status is labelled honestly. A check date remains visible and does not imply real-time verification. Missing coordinates produce no fabricated pin. Registry filtering/cleaning belongs to the backend.

### Account and pet resources

- `GET me/`: `{id,display_name,email,groups,merchant}`. `groups` must be an array supplied by the authenticated backend; `merchant` is null or `{id,name,slug}`. Membership of `merchant` enables the merchant workspace in the UI; backend permissions remain mandatory.
- `GET/POST pets/`: `{id,name,species,breed,sex,date_of_birth,microchip_no,allergies,diet_notes,weight_kg?,photo_url?}`. `allergies` is an array; nullable date/microchip fields are supported for display. POST omits ID and ownership. Species values follow the draft model (`dog`, `cat`, `rabbit`, `bird`, `other`).
- `GET/POST pets/{id}/records/`: `{id,name,record_type,date,next_due,clinic}`. POST omits ID. The frontend shows next-due suggestions in the reminder-creation picker; it does not assume that saving a record implicitly creates a reminder.
- `GET/POST reminders/`: `{id,pet,title,due_at,done}`. Creation sends `pet,title,due_at` and optional `health_record`; dates selected in the UI are sent at 09:00 Singapore time. `PATCH reminders/{id}/` sends `{done}`.
- `GET pets/{id}/documents/`: `{id,title,content_type,size_bytes,uploaded_at,download_url}`. `download_url` is a short-lived private GET URL.
- `POST pets/{id}/documents/`: input `{title,filename,content_type,size_bytes}`; output `{document:<document row>,upload_url:<presigned PUT URL>}`. The browser PUTs the file directly to that URL with matching Content-Type. Backend/storage must handle upload completion and reject unavailable/incomplete objects on download. If transfer fails, the frontend attempts `DELETE pets/{id}/documents/{document_id}/` to clean up metadata. Allowed UI types are PDF/JPEG/PNG up to 10 MB; server-side MIME/size/ownership enforcement is required.

Optional `photo_url` is a short-lived, owner-authorized GET URL. The frontend fetches it with no application Authorization header and renders a temporary blob URL, revoking it on changes/unmount. Missing or unavailable photos use a neutral species placeholder. Photo upload is not implemented in this slice; its presigned upload/completion lifecycle still needs to be connected if required for launch.

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
