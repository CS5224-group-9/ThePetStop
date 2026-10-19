import { Suspense } from "react";
import { Orders } from "@/components/marketplace";
import { AuthGate } from "@/components/shell";
export default function Page() {
  return (
    <AuthGate>
      <Suspense fallback={<p>Opening essentials…</p>}>
        <Orders detail />
      </Suspense>
    </AuthGate>
  );
}
