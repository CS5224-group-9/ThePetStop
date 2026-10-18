import { ResourceState } from "@/components/resource-state";
import { Merchant } from "@/components/merchant";
import { AuthGate } from "@/components/shell";
export default function Page() {
  return (
    <AuthGate merchant>
      <ResourceState domain="merchant">
        <Merchant />
      </ResourceState>
    </AuthGate>
  );
}
