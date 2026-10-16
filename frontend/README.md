This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
yarn dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

## Lint and format

ESLint checks the code (`eslint.config.mjs`) and Prettier formats it (`.prettierrc.json`, which also sorts Tailwind classes). CI runs these checks on every pull request, so run them before you push:

```bash
yarn lint
yarn format:check
```

Fix what ESLint can fix automatically, and reformat the code:

```bash
yarn lint --fix
yarn format
```

From the repository root, add `--cwd frontend`, for example `yarn --cwd frontend lint`.

The project uses Yarn 1. If `yarn` is not found, run `corepack enable` once (as administrator on Windows), or prefix the commands with `corepack`, as in `corepack yarn lint`.

## Fonts

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.
