import type { Metadata } from "next";
import { AppProvider } from "@/components/app-provider";
import { Shell } from "@/components/shell";
import "maplibre-gl/dist/maplibre-gl.css";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "PetStop SG · Singapore pet care workspace",
    template: "%s · PetStop SG",
  },
  referrer: "no-referrer",
  icons: { icon: { url: "/petstop-mark.svg", type: "image/svg+xml" } },
  description:
    "Your pets, their care, and Singapore’s pet essentials. Pet profiles, care records, facility discovery and a multi-merchant marketplace.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en-SG">
      <body>
        <AppProvider>
          <Shell>{children}</Shell>
        </AppProvider>
      </body>
    </html>
  );
}
