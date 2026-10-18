import { ResourceState } from "@/components/resource-state";
import { Suspense } from "react";
import { Checkout } from "@/components/marketplace";
import { AuthGate } from "@/components/shell";
export default function Page() {
  return (
    <AuthGate>
      <ResourceState domain="cart">
        <Suspense fallback={<p>Opening essentials…</p>}>
          <Checkout />
        </Suspense>
      </ResourceState>
    </AuthGate>
  );
}
