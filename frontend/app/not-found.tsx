import Link from "next/link";
export default function NotFound() {
  return (
    <section className="empty">
      <h1>Page not found</h1>
      <p>This page may have moved or is no longer available.</p>
      <Link className="button" href="/">
        Return to PetStop SG
      </Link>
    </section>
  );
}
