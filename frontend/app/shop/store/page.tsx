import { Suspense } from "react";
import { Shop } from "@/components/marketplace";

export default function Page() {
  return (
    <Suspense fallback={<p>Opening shop…</p>}>
      <Shop storefront />
    </Suspense>
  );
}
