<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

# Frontend agent guidance

These instructions apply to files under `frontend/`. Keep them outside the generated block above. Product scope and the draft route layout are in `../docs/product-context.md` and `../docs/repository-structure.md`.

## Current frontend

- Next.js App Router with React, TypeScript, and Tailwind CSS. Check `package.json` for versions.
- Only the default `create-next-app` page exists. There is no API client, map library, or test runner yet.
- Dependency management is Yarn. Use `yarn add` and `yarn remove`, and commit `yarn.lock`. Do not create `package-lock.json`.

## Implementation guidelines

- Build only the requested slice of the prototype: pet profiles, the facility map and directory, or the marketplace with simulated checkout.
- Call the Django API through one shared client module instead of scattering `fetch` calls. Read the API base URL from an environment variable; do not hardcode `127.0.0.1:8000`.
- Match the backend's URLs, payloads, authentication, and error format. When a task changes a contract, change both sides.
- The backend enforces ownership of pet data. The frontend must still handle `401`, `403`, and `404` responses, and must not cache one user's pet records where another user could see them.
- Veterinary documents and pet photos are private. Do not place their URLs in query strings, logs, or analytics.
- The report names MapLibre for the map and Jest for tests. Neither is installed; add one only when a task needs it.
- Label simulated checkout as simulated. Never show wording that implies a real charge.
- Show AVS licence status as returned by the backend. Do not present mock or stale facility data as official registry data.

## Working locally

From `frontend/`: `yarn install`, `yarn dev`, `yarn lint`, `yarn build`.
