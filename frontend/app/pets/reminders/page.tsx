import { ResourceState } from "@/components/resource-state";
import { Suspense } from "react";
import { Reminders } from "@/components/pets";
import { AuthGate } from "@/components/shell";
export default function Page() {
  return (
    <AuthGate>
      <ResourceState domain="reminders">
        <Suspense fallback={<p>Opening passport…</p>}>
          <Reminders />
        </Suspense>
      </ResourceState>
    </AuthGate>
  );
}
