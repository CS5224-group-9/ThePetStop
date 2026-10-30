// LOCAL DEVELOPMENT ONLY: sign in as a seeded user with `Authorization: Dev <handle>`.
// It is honoured only when NEXT_PUBLIC_DEV_AUTH=true, in API mode, on
// localhost/127.0.0.1; the backend independently requires DEBUG, its own
// opt-in and a loopback client. Never touch the browser at module top level.
import { ApiError } from "../api/client.ts";

export const DEV_USERS = [
  {
    handle: "alice",
    name: "Alice",
    role: "owner",
    description: "Pet owner with Kopi and Mochi",
  },
  {
    handle: "bob",
    name: "Bob",
    role: "owner",
    description: "Pet owner with Sesame and Nemo",
  },
  {
    handle: "mira",
    name: "Mira",
    role: "merchant",
    description: "Merchant who also owns Biscuit",
  },
] as const;

// Literal `process.env.NEXT_PUBLIC_*` access so Next inlines the values at build time.
const FLAG = process.env.NEXT_PUBLIC_DEV_AUTH === "true";
const API_MODE = process.env.NEXT_PUBLIC_DATA_SOURCE === "api";

export function isDevAuthAllowed(
  flag: boolean,
  apiMode: boolean,
  hostname: string | undefined,
): boolean {
  return (
    flag && apiMode && (hostname === "localhost" || hostname === "127.0.0.1")
  );
}

export function devAuthEnabled(): boolean {
  return isDevAuthAllowed(
    FLAG,
    API_MODE,
    typeof window === "undefined" ? undefined : window.location.hostname,
  );
}

const key = "petstop.dev-user";
const isHandle = (value: unknown): value is string =>
  DEV_USERS.some((user) => user.handle === value);

/** The signed-in development handle of this tab, or null. */
export function devHandle(): string | null {
  try {
    if (typeof window === "undefined") return null;
    const value = window.sessionStorage.getItem(key);
    return isHandle(value) ? value : null;
  } catch {
    return null;
  }
}

export function setDevHandle(handle: string): void {
  try {
    if (typeof window !== "undefined")
      window.sessionStorage.setItem(key, handle);
  } catch {
    /* Storage may be blocked; sign-in then reports a failure. */
  }
}

export function clearDevHandle(): void {
  try {
    if (typeof window !== "undefined") window.sessionStorage.removeItem(key);
  } catch {
    /* Nothing secret is stored here. */
  }
}

export function devSignInError(error: unknown): string {
  if (error instanceof ApiError && error.status === 401)
    return "The API did not accept the development sign-in. Set DJANGO_DEBUG=True and DJANGO_DEV_AUTH=true in backend/.env, restart Django, and open the site at http://localhost:3000.";
  if (error instanceof ApiError && error.code === "network_error")
    return "Cannot reach the API at NEXT_PUBLIC_API_BASE_URL. Is Django running?";
  if (error instanceof Error) return error.message;
  return "Development sign-in failed. Please try again.";
}
