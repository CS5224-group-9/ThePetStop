"use client";
import { useApp } from "./app-provider";
import type { Domain } from "@/lib/api/types";
export function ResourceState({
  domain,
  children,
}: {
  domain: Domain;
  children: React.ReactNode;
}) {
  const { resources, refresh } = useApp();
  const status = resources[domain];
  if (status.loading && !status.loaded)
    return (
      <div className="panel resource-loading" role="status" aria-live="polite">
        <span className="loading-spinner" />
        Loading…
      </div>
    );
  if (status.error && !status.loaded)
    return (
      <div className="panel service-error" role="alert">
        <h2>Unable to load this content</h2>
        <p>{status.error}</p>
        <button
          className="button secondary"
          onClick={() => void refresh(domain)}
        >
          Try again
        </button>
      </div>
    );
  return (
    <div aria-busy={status.loading}>
      {status.error && (
        <div className="refresh-error" role="alert">
          <p>{status.error}</p>
          <button className="text-button" onClick={() => void refresh(domain)}>
            Retry refresh
          </button>
        </div>
      )}
      {children}
    </div>
  );
}
export function FormError({ message }: { message: string }) {
  return message ? (
    <p className="form-error" role="alert">
      {message}
    </p>
  ) : null;
}
