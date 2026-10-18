import { Suspense } from "react";
import { Login } from "@/components/login";
export default function Page() {
  return (
    <Suspense fallback={<p>Loading sign-in…</p>}>
      <Login />
    </Suspense>
  );
}
