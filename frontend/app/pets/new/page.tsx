import { Suspense } from "react";
import { NewPet } from "@/components/pets";
import { AuthGate } from "@/components/shell";
export default function Page() {
  return (
    <AuthGate>
      <Suspense fallback={<p>Opening passport…</p>}>
        <NewPet />
      </Suspense>
    </AuthGate>
  );
}
