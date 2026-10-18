# PetStop SG frontend

## Standalone UI (default)

Run `yarn install --frozen-lockfile` then `yarn dev`. No environment configuration, backend or sign-in is required. `NEXT_PUBLIC_DATA_SOURCE=local` is the default, even if an API URL is present. Restart/rebuild after changing this setting.

The dashboard, three sample pets, six fictional shops (24 products per shop), price comparison, local cart, simulated checkout, order history and merchant workspace are usable immediately. Pet registration, care records, reminders and merchant changes save in this browser’s local storage. This is a single local workspace, not a secure account; use sample information. Clearing site storage resets it. If storage is blocked or full, browsing still works but saving shows an error.

Facility search and filters use clearly fictional listings and an offline schematic map with selectable pins. Directions open an external map. Document selection and download work within the current tab; files are kept in memory and disappear on reload. No files are uploaded.

To enable the existing API integration later, set `NEXT_PUBLIC_DATA_SOURCE=api` and the API/Cognito values in `.env.example`. Local mode never activates as a fallback for failed API requests. The remainder of this document describes **API mode only**.

## API mode

Next.js App Router frontend for the Singapore pet-care MVP. It retains the clinical visual system and static S3/CloudFront export, but now uses API-backed state and Cognito sign-in. There is no demo account picker, embedded catalogue, sample pet roster, browser-backed database or local checkout implementation.

The Django backend remains separate and currently has no feature endpoints. Until the API and Cognito are configured, the frontend shows service-unavailable/sign-in-unavailable states. A successful static build does not certify a live production deployment.

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

Public: `/`, `/login/`, `/auth/callback/`, `/map/`, `/shop/`, `/shop/product/?id=…`.

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
