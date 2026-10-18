import { ResourceState } from "@/components/resource-state";
import { Suspense } from "react";
import { PetDetail } from "@/components/pets";
import { AuthGate } from "@/components/shell";
export default function Page() {
  return (
    <AuthGate>
      <ResourceState domain="pets">
        <Suspense fallback={<p>Opening passport…</p>}>
          <PetDetail />
        </Suspense>
      </ResourceState>
    </AuthGate>
  );
}
