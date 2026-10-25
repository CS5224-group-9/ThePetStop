"use client";
import Link from "next/link";
import { localUI } from "@/lib/data-source";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { useApp } from "./app-provider";
import { Icon } from "./ui";
import { nextPath } from "@/lib/format";

const navigation = [
  { href: "/", label: "Overview", mobile: "Home", icon: "grid" },
  { href: "/map/", label: "Map & facilities", mobile: "Map", icon: "map" },
  {
    href: "/pets/",
    label: "Pet passports & health",
    mobile: "Pets",
    icon: "paw",
  },
  { href: "/shop/", label: "Pet marketplace", mobile: "Shop", icon: "bag" },
  { href: "/orders/", label: "Orders", mobile: "Orders", icon: "box" },
];
export function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const { state, notice, signOut, notify } = useApp();
  const active =
    path.startsWith("/cart") || path.startsWith("/checkout") ? "/shop/" : path;
  const count = state.cart.reduce((sum, item) => sum + item.quantity, 0);
  const isActive = (href: string) =>
    href === "/" ? active === "/" : active.startsWith(href);
  return (
    <>
      <a href="#main-content" className="skip-link">
        Skip to content
      </a>
      <header className="topbar">
        <div className="topbar-inner">
          <Link href="/" className="brand" aria-label="PetStop SG home">
            <span className="brand-icon">
              <Icon name="medical" size={25} />
            </span>
            <span>
              PetStop SG<small>Singapore pet care workspace</small>
            </span>
          </Link>
          <nav className="desktop-nav" aria-label="Main navigation">
            {navigation.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                aria-current={isActive(item.href) ? "page" : undefined}
              >
                {item.label}
              </Link>
            ))}
          </nav>
          <div className="header-actions">
            <Link
              href="/pets/reminders/"
              className="icon-button reminders-link"
              aria-label="Care reminders"
            >
              <Icon name="bell" />
            </Link>
            <Link
              href="/cart/"
              className="icon-button"
              aria-label={`Cart, ${count} items`}
            >
              <Icon name="bag" />
              <span className="count">{count}</span>
            </Link>
            {state.role ? (
              <details className="account-menu">
                <summary className="account" aria-label="Account options">
                  <span className="avatar">
                    <Icon name="user" size={18} />
                  </span>
                  <span>
                    {state.profile?.display_name || "Account"}
                    <small>
                      {localUI
                        ? "Local workspace"
                        : state.role === "merchant"
                          ? "Merchant"
                          : "Pet owner"}
                    </small>
                  </span>
                  <span className="account-chevron">⌄</span>
                </summary>
                <div className="account-options">
                  <Link href="/pets/">Pet profiles</Link>
                  <Link href="/merchant/">Merchant workspace</Link>
                  {!localUI && (
                    <button
                      onClick={() =>
                        void signOut().catch((error) =>
                          notify(
                            error instanceof Error
                              ? error.message
                              : "Unable to sign out.",
                          ),
                        )
                      }
                    >
                      Sign out
                    </button>
                  )}
                </div>
              </details>
            ) : (
              <Link className="button small" href="/login/">
                Sign in <Icon name="arrow" size={16} />
              </Link>
            )}
          </div>
        </div>
      </header>
      <div className="workspace">
        <main id="main-content" tabIndex={-1}>
          {children}
        </main>
        <footer>
          <div className="footer-brand">
            <Icon name="medical" size={17} />
            <span>
              © 2026 PetStop SG{" "}
              <small>Singapore pet care · Simulated checkout</small>
            </span>
          </div>
          <div>
            <Link href="/map/">Facility directory</Link>
            <Link href="/pets/reminders/">Care reminders</Link>
            <Link href="/merchant/">Merchant workspace</Link>
          </div>
        </footer>
      </div>
      <nav className="mobile-nav" aria-label="Mobile navigation">
        {navigation.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            aria-current={isActive(item.href) ? "page" : undefined}
          >
            <Icon name={item.icon} />
            <span>{item.mobile}</span>
          </Link>
        ))}
      </nav>
      <div
        className={`toast ${notice ? "visible" : ""}`}
        role="status"
        aria-live="polite"
      >
        {notice && (
          <>
            <Icon name="check" />
            {notice}
          </>
        )}
      </div>
    </>
  );
}
export function AuthGate({
  children,
  merchant = false,
}: {
  children: React.ReactNode;
  merchant?: boolean;
}) {
  const { state, authStatus, authError, retryAuth } = useApp();
  const path = usePathname();
  const [returnTo, setReturnTo] = useState(path);
  useEffect(() => {
    queueMicrotask(() =>
      setReturnTo(nextPath(window.location.pathname + window.location.search)),
    );
  }, [path]);
  if (authStatus === "loading")
    return (
      <div className="panel resource-loading" role="status">
        <span className="loading-spinner" />
        Checking your session…
      </div>
    );
  if (authStatus === "error")
    return (
      <div className="panel service-error" role="alert">
        <h1>Unable to load your account</h1>
        <p>{authError}</p>
        <button className="button secondary" onClick={retryAuth}>
          Try again
        </button>
      </div>
    );
  if (!state.role)
    return (
      <div className="auth-card">
        <div className="hero-icon">
          <Icon name="shield" size={32} />
        </div>
        <span className="eyebrow">YOUR PET CARE WORKSPACE</span>
        <h1>Sign in to continue</h1>
        <p>Access your pets, care records, basket and order history.</p>
        <Link
          className="button"
          href={`/login/?next=${encodeURIComponent(returnTo)}`}
        >
          Sign in
          <Icon name="arrow" size={18} />
        </Link>
      </div>
    );
  if (merchant && !localUI && state.role !== "merchant")
    return (
      <div className="empty">
        <h1>Merchant access required</h1>
        <p>Your account does not have access to the merchant workspace.</p>
        <Link className="button secondary" href="/">
          Return to overview
        </Link>
      </div>
    );
  return children;
}
