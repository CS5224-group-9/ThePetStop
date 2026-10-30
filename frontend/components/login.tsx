"use client";
import Link from "next/link";
import { localUI } from "@/lib/data-source";
import { useSearchParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useApp } from "./app-provider";
import { Icon } from "./ui";
import { authConfigured, finishSignIn, signIn } from "@/lib/auth/cognito";
import { DEV_USERS, devAuthEnabled, devHandle } from "@/lib/auth/dev";
import { nextPath } from "@/lib/format";
import { FormError } from "./resource-state";
function LoginStory() {
  return (
    <section className="login-story">
      <Icon name="medical" size={44} />
      <span className="eyebrow">PETSTOP SG / ACCOUNT ACCESS</span>
      <h1>
        A single workspace
        <br />
        for pet care.
      </h1>
      <p>
        Manage pet profiles, review care records and find supplies across
        Singapore’s pet marketplace.
      </p>
      <small>PetStop SG · Singapore pet care workspace</small>
    </section>
  );
}
export function Login() {
  const { state, signInDev } = useApp();
  const params = useSearchParams();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (localUI)
    return (
      <div className="auth-card">
        <span className="eyebrow">YOUR PET CARE WORKSPACE</span>
        <h1>Everything in one place</h1>
        <p>
          Explore pet profiles, discover facilities and shop across six
          fictional stores. No sign-in is needed. Changes stay in this browser;
          use sample information.
        </p>
        <Link className="button" href={nextPath(params.get("next"), "/")}>
          Open workspace <Icon name="arrow" size={18} />
        </Link>
      </div>
    );
  if (devAuthEnabled()) {
    // LOCAL DEVELOPMENT ONLY: devAuthEnabled() needs NEXT_PUBLIC_DEV_AUTH=true,
    // API mode and a localhost/127.0.0.1 hostname.
    const current = state.role ? devHandle() : null;
    return (
      <div className="login-layout">
        <LoginStory />
        <section className="login-form">
          <span className="eyebrow">LOCAL DEVELOPMENT</span>
          <h2>Choose a development user</h2>
          <p>
            Development sign-in for this computer only. It is unavailable on
            deployed sites and uses seeded sample data.
          </p>
          <FormError message={error} />
          <div className="dev-login-list">
            {DEV_USERS.map((user) => (
              <button
                className="button secondary"
                key={user.handle}
                disabled={busy}
                onClick={async () => {
                  setError("");
                  setBusy(true);
                  try {
                    await signInDev(user.handle);
                    router.replace(nextPath(params.get("next"), "/"));
                  } catch (cause) {
                    setError(
                      cause instanceof Error
                        ? cause.message
                        : "Development sign-in failed. Please try again.",
                    );
                    setBusy(false);
                  }
                }}
              >
                <span>
                  {current === user.handle
                    ? `Signed in as ${user.name}`
                    : `Sign in as ${user.name}`}
                  <small>{user.description}</small>
                </span>
                {current === user.handle ? (
                  <Icon name="check" size={18} />
                ) : (
                  <Icon name="arrow" size={18} />
                )}
              </button>
            ))}
          </div>
          {state.role && (
            <Link
              className="text-link"
              href={nextPath(params.get("next"), "/")}
            >
              Continue to workspace
              <Icon name="arrow" size={16} />
            </Link>
          )}
        </section>
      </div>
    );
  }
  return (
    <div className="login-layout">
      <LoginStory />
      <section className="login-form">
        <span className="eyebrow">WELCOME TO PETSTOP SG</span>
        <h2>{state.role ? "You’re signed in" : "Sign in to your account"}</h2>
        <p>
          Continue through our secure sign-in service. Your account determines
          which workspace you can access.
        </p>
        <FormError message={error} />
        {state.role ? (
          <Link className="button" href={nextPath(params.get("next"), "/")}>
            Continue to workspace
            <Icon name="arrow" size={18} />
          </Link>
        ) : (
          <button
            className="button"
            disabled={busy || !authConfigured()}
            onClick={async () => {
              setBusy(true);
              setError("");
              try {
                await signIn(nextPath(params.get("next")));
              } catch (cause) {
                setError(
                  cause instanceof Error
                    ? cause.message
                    : "Unable to start sign-in. Please try again.",
                );
                setBusy(false);
              }
            }}
          >
            {busy ? "Opening secure sign-in…" : "Continue to secure sign-in"}
            <Icon name="arrow" size={18} />
          </button>
        )}
        {!authConfigured() && (
          <p className="info-note" role="status">
            Sign-in is temporarily unavailable. Please try again later.
          </p>
        )}
        <Link className="text-link" href="/shop/">
          Browse products without signing in
          <Icon name="arrow" size={16} />
        </Link>
      </section>
    </div>
  );
}
export function AuthCallback() {
  const router = useRouter();
  const started = useRef(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    if (localUI || devAuthEnabled()) {
      router.replace("/");
      return;
    }
    finishSignIn()
      .then((path) => router.replace(path))
      .catch(() => {
        window.history.replaceState({}, "", window.location.pathname);
        setError(
          "Sign-in could not be completed. Start again from the sign-in page.",
        );
      });
  }, [router]);
  return (
    <div className="auth-card">
      {error ? (
        <>
          <h1>Unable to sign in</h1>
          <FormError message={error} />
          <Link className="button" href="/login/">
            Return to sign-in
          </Link>
        </>
      ) : (
        <div role="status">
          <span className="loading-spinner" />
          <h1>Completing sign-in…</h1>
        </div>
      )}
    </div>
  );
}
