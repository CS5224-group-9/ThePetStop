"use client";
import Link from "next/link";
export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <section className="panel service-error" role="alert">
      <h1>Unable to display this page</h1>
      <p>Please try again. If the problem continues, return to the overview.</p>
      <button className="button" onClick={reset}>
        Try again
      </button>
      <Link className="button secondary" href="/">
        Return to overview
      </Link>
    </section>
  );
}
