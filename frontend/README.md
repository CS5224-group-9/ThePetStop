# PetStop SG frontend

## Standalone UI (default)

Run `yarn install --frozen-lockfile` then `yarn dev`. No environment configuration, backend or sign-in is required. `NEXT_PUBLIC_DATA_SOURCE=local` is the default, even if an API URL is present. Restart/rebuild after changing this setting.

The dashboard, three sample pets, six fictional shops (24 products per shop), shop storefronts, price comparison, local cart, simulated checkout, order history and merchant workspace are usable immediately. Pet registration, care records, reminders and merchant changes save in this browser’s local storage. This is a single local workspace, not a secure account; use sample information. Clearing site storage resets it. If storage is blocked or full, browsing still works but saving shows an error.

Facility search and filters use clearly fictional listings and a live OneMap basemap rendered by MapLibre with selectable sample pins. Search, type filters, compact facility rows and the map share one responsive workspace. Facility details appear below it only after selecting a listing or pin; no facility panel covers the map. Selecting a facility centres its pin, and the details can be dismissed. Design rationale and manual checks: [facility map design](../docs/facility-map-design.md). The basemap requires internet access; the facility list remains available if tiles fail. On each visit, a dismissible prompt offers “Use my location” or “Not now”; permission is requested only after choosing to use location. “Use my current location” asks for browser permission, centres the map and shows a blue marker with reported accuracy. It requires HTTPS or localhost, keeps coordinates only in page memory, and handles denied permission, timeouts and positions outside map coverage. One location-search field accepts addresses, landmarks and postal codes. Selecting an address or using device location shows nearby facilities, nearest first, with a kilometre-radius filter and a matching search area on the map. No OneMap credentials or backend are needed for the basemap or browser geolocation. Directions open an external map. Document selection and download work within the current tab; files are kept in memory and disappear on reload. No files are uploaded.

To enable the existing API integration later, set `NEXT_PUBLIC_DATA_SOURCE=api` and the API/Cognito values in `.env.example`. Local mode never activates as a fallback for failed API requests. The remainder of this document describes **API mode only**.

## API mode

Next.js App Router frontend for the Singapore pet-care MVP. It retains the clinical visual system and static S3/CloudFront export, but now uses API-backed state and Cognito sign-in. There is no demo account picker, embedded catalogue, sample pet roster, browser-backed database or local checkout implementation.

The Django backend now includes public marketplace catalogue endpoints; pet, facility, cart, checkout, order and merchant write endpoints remain separate integration work. Until the API and Cognito are configured, the frontend shows service-unavailable/sign-in-unavailable states. A successful static build does not certify a live production deployment.

## Run locally

```bash
yarn install --frozen-lockfile
```

Copy `.env.example` to `.env.local` and set the public API/Cognito configuration. Then:

```bash
yarn dev
```

Configuration is read at build time. Rebuild after changing it. No `NEXT_PUBLIC_*` value may contain a client secret, AWS key or other credential. The API base includes `/api/v1/`.

See [frontend integration](../docs/frontend-integration.md) for the response contract and deployment settings the backend/infrastructure team must supply.

## Authentication and privacy

- Cognito authorization-code flow with PKCE is handled by `oidc-client-ts`; the SPA app client must not have a secret. `/auth/callback/` processes the authorization response and removes callback parameters from browser history.
- Access, ID and refresh tokens stay in memory. Session storage contains temporary OIDC transaction state and a single non-sensitive session-presence flag; it contains no pet records or tokens. A full reload can restore Cognito SSO through a top-level authorization redirect. If the identity-provider session has expired, sign-in is required again.
- `/me/` supplies the account name, groups and merchant membership. There is no frontend role selector. API authentication/authorization and record ownership must still be enforced by the backend.
- Sign-out and session expiry clear private UI state. Stale read and mutation responses are discarded after the active account changes. Private requests and signed file transfers use `no-store`, omit ambient credentials and do not send referrer URLs.
- Reports upload directly to a backend-issued presigned URL. Downloads use a freshly fetched signed URL and a temporary blob download; no signed document URL is added to application navigation. File type/size checks in the browser complement, and do not replace, backend/S3 validation.

## Data boundary

`lib/api/client.ts` owns API calls, authorization headers, timeout/error handling and bounded pagination. `services.ts` maps documented endpoints to operations. `adapters.ts` translates the provisional wire contract to UI models; it rejects malformed IDs and monetary values. There are no fallback records.

For this bounded MVP catalogue, lists are collected across paginated API responses (maximum 100 pages) before local search/filtering. Public catalogue/facility data stays in memory; private data is discarded on account changes. A large/unbounded catalogue should use server-driven search and page controls rather than increasing this limit.

All writes wait for a server response. Basket writes send product IDs and quantities, not prices. Checkout sends delivery details and an idempotency key; the server calculates totals, validates stock, splits merchants and commits the order. The UI labels payment as simulated, as required by MVP scope. Merchant updates use merchant-only endpoints, never edit a shared local catalogue.

## Pages and interactions

Public: `/`, `/login/`, `/auth/callback/`, `/map/`, `/shop/`, `/shop/product/?id=product-id`, `/shop/store/?merchant=shop-slug`.

Signed-in: `/pets/`, `/pets/new/`, `/pets/detail/?id=…`, `/pets/reminders/`, `/cart/`, `/checkout/`, `/orders/`, `/orders/detail/?id=…`.

Merchant membership: `/merchant/`.

Pet creation, care records, manual/suggested reminders, reminder completion, report upload/download, merchant price/stock changes, fulfilment status, basket changes and checkout use the API. Facility pins use API coordinates on MapLibre with OneMap tiles and required attribution. Missing map tiles do not prevent list browsing and directions. Verification status and check dates come from the API; the frontend does not certify licences or invent opening hours.

The UI supports loading, empty, error, permission and session-expired states, visible focus, keyboard-operated tabs, reduced motion, responsive layouts and automatic dark appearance. Product and pet fallbacks are neutral placeholders, not fictional photographs or implied real inventory. Optional private pet-photo URLs from the API are fetched into revocable, in-memory blob URLs.

## Checks

Node 22.6+ is needed for the built-in TypeScript test runner (CI uses Node 24).

```bash
yarn lint
yarn format:check
yarn tsc --noEmit
yarn test
yarn build
```

`yarn build` exports `out/`; `next start` is not the server for a static export. Frontend CI now runs lint, formatting, contract tests and the static build.

Tests inject HTTP responses into the real client/service boundary. `tests/support/contract-server.mjs` is an explicit test-only API/OIDC fixture for browser integration checks; it is not imported by the application and is not a backend implementation. Browser validation against that fixture does not validate an actual Cognito pool, Django ownership rules, S3 policies or the live registry feed.

Design rationale: [frontend design review](../docs/frontend-design-review.md). The backend, real payments, bookings, community features and out-of-scope notifications are not implemented by this frontend change.

## Live location search with local sample facilities

Keep `NEXT_PUBLIC_DATA_SOURCE=local` and set `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1/` in `frontend/.env.local`. Configure `ONEMAP_EMAIL` and `ONEMAP_PASSWORD` only in `backend/.env`, and allow `http://localhost:3000` in `DJANGO_CORS_ALLOWED_ORIGINS`. Run Django on port 8000 and `yarn dev` from `frontend/`; restart both after configuration changes. No Cognito setup is needed for location search.

Enter an address, landmark or postal code, press Search and choose a matching location. The sidebar shows facilities rather than mixed facility/place suggestions. A pin identifies a searched address; a blue dot identifies device location. Changing/clearing the query cancels pending requests and discards stale results. Selecting a search result supersedes pending device-location responses. Clearing the search resets the centre, removes the radius boundary and returns to browsing all facilities.

Search returns up to 10 matches from OneMap's first page. No matches, invalid upstream results, missing configuration and service failures have distinct handling; failed requests do not fall back to sample addresses. The form fetches addresses on explicit submission and uses keyboard-accessible result buttons rather than a combobox. Escape dismisses suggestions without clearing the query; Clear resets the text and suggestions. Category filters remain active after selecting a location. Failed searches retain the previous selected centre and its facility results. Device coordinates remain in page memory; entered search text is sent to the backend and OneMap. Facility registry ingestion and production search hosting remain separate work.

Manual check: search `Bishan`, select an address and verify the centre, radius boundary and nearby results; try a six-digit postal code; edit/clear while a search is pending; test no matches, denied geolocation, and unavailable backend; verify light/dark appearance and narrow layouts. Live OneMap calls require your configured account and are not exercised by automated tests.

## MapLibre worker asset

`yarn dev` and `yarn build` automatically run `scripts/prepare-maplibre-worker.mjs`. It copies the worker and licence from the installed MapLibre package into ignored `public/maplibre/<version>/`. The map explicitly uses that same-origin, versioned worker URL; Next.js bundling otherwise breaks MapLibre's module-relative worker lookup. The static export includes this asset for S3/CloudFront, so no CDN or Next.js server route is needed.

If invoking Next.js directly rather than using the Yarn scripts, run `node scripts/prepare-maplibre-worker.mjs` first. A “Worker failed to load” error is a worker asset problem, not a OneMap tile/token problem. In development, actual MapLibre errors are logged with the `[Facility map]` prefix. Successful OneMap tile events clear temporary map-content warnings.

## Nearby facility radius

The location-first flow is: choose an address or device location → choose a radius → browse facilities nearest first. Radius options are 1, 2, 5 (default), 10 and 20 km, plus All Singapore. Before a centre is chosen, radius is disabled and the directory shows all facilities. The radius selector applies equally to the list and facility pins; changing it also fits the map to the search area.

Distances are straight-line haversine distances, computed from the already-loaded facility coordinates; they are not driving/walking distances. Facilities with unknown/invalid coordinates are excluded from a bounded radius, and appear last with “Distance unavailable” in All Singapore. No facility coordinates or registry verification are invented. Sample coordinates remain approximate and fictional. Vet/shop and emergency filters apply within the radius. Clear filters restores 5 km and all categories while preserving the centre; Clear search removes the centre.

A dashed boundary shows the selected radius. It represents the search area, not device-location accuracy. The blue dot is reserved for device location; searched addresses use a pin. The calculation currently runs in the frontend against the bounded catalogue; future backend-driven pagination must apply radius filtering on the server before pagination.
