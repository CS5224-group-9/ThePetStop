import { ResourceState } from "@/components/resource-state";
import { Suspense } from "react";
import { Pets } from "@/components/pets";
import { AuthGate } from "@/components/shell";
export default function Page() {
  return (
    <AuthGate>
      <ResourceState domain="pets">
        <Suspense fallback={<p>Opening passport…</p>}>
          <Pets />
        </Suspense>
      </ResourceState>
    </AuthGate>
  );
}
