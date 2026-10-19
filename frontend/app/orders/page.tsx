import { ResourceState } from "@/components/resource-state";
import { Suspense } from "react";
import { Orders } from "@/components/marketplace";
import { AuthGate } from "@/components/shell";
export default function Page() {
  return (
    <AuthGate>
      <ResourceState domain="orders">
        <Suspense fallback={<p>Opening essentials…</p>}>
          <Orders />
        </Suspense>
      </ResourceState>
    </AuthGate>
  );
}
