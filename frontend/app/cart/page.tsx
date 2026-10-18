import { ResourceState } from "@/components/resource-state";
import { Suspense } from "react";
import { Cart } from "@/components/marketplace";
import { AuthGate } from "@/components/shell";
export default function Page() {
  return (
    <AuthGate>
      <ResourceState domain="cart">
        <Suspense fallback={<p>Opening essentials…</p>}>
          <Cart />
        </Suspense>
      </ResourceState>
    </AuthGate>
  );
}
