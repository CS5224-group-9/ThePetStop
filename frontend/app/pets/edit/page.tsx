import { ResourceState } from "@/components/resource-state";
import { Suspense } from "react";
import { EditPet } from "@/components/pets";
import { AuthGate } from "@/components/shell";
export default function Page() {
  return (
    <AuthGate>
      <ResourceState domain="pets">
        <Suspense fallback={<p>Opening passport…</p>}>
          <EditPet />
        </Suspense>
      </ResourceState>
    </AuthGate>
  );
}
