import {
  InMemoryWebStorage,
  UserManager,
  WebStorageStateStore,
} from "oidc-client-ts";
import { nextPath } from "../format";
import { validateServiceUrl } from "../api/client";

const sessionKey = "petstop.session-present";
export function canRestoreSession() {
  try {
    return window.sessionStorage.getItem(sessionKey) === "1";
  } catch {
    return false;
  }
}
export function rememberSession() {
  try {
    window.sessionStorage.setItem(sessionKey, "1");
  } catch {
    /* Sign-in still works without storage persistence. */
  }
}
export function forgetSession() {
  try {
    window.sessionStorage.removeItem(sessionKey);
  } catch {
    /* No credentials or records are stored here. */
  }
}
let manager: UserManager | null = null;
export function authConfigured() {
  return Boolean(
    process.env.NEXT_PUBLIC_COGNITO_DOMAIN &&
    process.env.NEXT_PUBLIC_COGNITO_CLIENT_ID &&
    process.env.NEXT_PUBLIC_COGNITO_ISSUER &&
    process.env.NEXT_PUBLIC_COGNITO_REDIRECT_URI &&
    process.env.NEXT_PUBLIC_COGNITO_LOGOUT_URI,
  );
}
export function getAuthManager() {
  if (!authConfigured())
    throw new Error("Sign-in is not available yet. Please try again later.");
  if (typeof window === "undefined")
    throw new Error("Sign-in requires a browser.");
  if (manager) return manager;
  const domain = validateServiceUrl(
    process.env.NEXT_PUBLIC_COGNITO_DOMAIN!,
  ).origin;
  const issuer = validateServiceUrl(
    process.env.NEXT_PUBLIC_COGNITO_ISSUER!,
  ).href.replace(/\/$/, "");
  const redirect = validateServiceUrl(
    process.env.NEXT_PUBLIC_COGNITO_REDIRECT_URI!,
  ).href;
  const logout = validateServiceUrl(
    process.env.NEXT_PUBLIC_COGNITO_LOGOUT_URI!,
  ).href;
  if (
    new URL(redirect).origin !== window.location.origin ||
    new URL(logout).origin !== window.location.origin
  )
    throw new Error("Sign-in is unavailable at this address.");
  manager = new UserManager({
    authority: issuer,
    client_id: process.env.NEXT_PUBLIC_COGNITO_CLIENT_ID!,
    redirect_uri: redirect,
    response_type: "code",
    scope: process.env.NEXT_PUBLIC_COGNITO_SCOPES || "openid email profile",
    metadata: {
      issuer,
      authorization_endpoint: `${domain}/oauth2/authorize`,
      token_endpoint: `${domain}/oauth2/token`,
      userinfo_endpoint: `${domain}/oauth2/userInfo`,
      jwks_uri: `${issuer}/.well-known/jwks.json`,
    },
    userStore: new WebStorageStateStore({ store: new InMemoryWebStorage() }),
    stateStore: new WebStorageStateStore({ store: window.sessionStorage }),
    automaticSilentRenew: true,
    loadUserInfo: false,
    revokeTokenTypes: ["refresh_token"],
    extraTokenParams: {},
    staleStateAgeInSeconds: 600,
  });
  return manager;
}
export async function signIn(returnTo = "/pets/", restore = false) {
  const auth = getAuthManager();
  await auth.clearStaleState();
  await auth.signinRedirect({
    state: { returnTo: nextPath(returnTo) },
    ...(restore ? { prompt: "none" } : {}),
  });
}
export async function signOut() {
  const auth = getAuthManager();
  forgetSession();
  const revocation = auth.revokeTokens(["refresh_token"]);
  await auth.removeUser();
  try {
    await revocation;
  } catch {
    /* Always remove local credentials, including during a network failure. */
  }
  const url = new URL(
    "/logout",
    validateServiceUrl(process.env.NEXT_PUBLIC_COGNITO_DOMAIN!),
  );
  url.searchParams.set("client_id", process.env.NEXT_PUBLIC_COGNITO_CLIENT_ID!);
  url.searchParams.set(
    "logout_uri",
    process.env.NEXT_PUBLIC_COGNITO_LOGOUT_URI!,
  );
  window.location.assign(url.href);
}
let callback: Promise<string> | null = null;
export async function finishSignIn() {
  // StrictMode may mount twice; an authorization code must only be redeemed once.
  callback ??= getAuthManager()
    .signinRedirectCallback()
    .then((user) => {
      rememberSession();
      const state = user.state as { returnTo?: unknown } | undefined;
      window.history.replaceState({}, "", window.location.pathname);
      return nextPath(state?.returnTo);
    })
    .catch((error) => {
      forgetSession();
      window.history.replaceState({}, "", window.location.pathname);
      throw error;
    });
  return callback;
}
