import { Suspense } from "react";
import { ProductDetail } from "@/components/marketplace";

export default function Page() {
  return (
    <Suspense fallback={<p>Opening essentials…</p>}>
      <ProductDetail />
    </Suspense>
  );
}
