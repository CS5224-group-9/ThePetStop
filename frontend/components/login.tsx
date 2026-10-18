"use client";
import Link from "next/link";
import { localUI } from "@/lib/data-source";
import { useSearchParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useApp } from "./app-provider";
import { Icon } from "./ui";
import { authConfigured, finishSignIn, signIn } from "@/lib/auth/cognito";
import { nextPath } from "@/lib/format";
import { FormError } from "./resource-state";
export function Login() {
  const { state } = useApp();
  const params = useSearchParams();
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
  return (
    <div className="login-layout">
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
    if (localUI) {
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
