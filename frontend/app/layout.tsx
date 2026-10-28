import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import "@fontsource/poppins/400.css";
import "@fontsource/poppins/500.css";
import "@fontsource/poppins/600.css";
import "@fontsource/poppins/700.css";
import "./globals.css";
import AuthShell from "@/components/AuthShell";
import { BRAND_METADATA } from "@/components/Brand";

export const metadata: Metadata = {
  title: BRAND_METADATA,
  description: "Freight commercial intelligence. Shared, authenticated access only.",
  manifest: "/manifest.json",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#0b0b0d" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en-GB">
      <body>
        <AuthShell>{children}</AuthShell>
      </body>
    </html>
  );
}
