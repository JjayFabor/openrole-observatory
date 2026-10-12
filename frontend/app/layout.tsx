import type { Metadata } from "next";
import "./globals.css";
import { getSiteOrigin } from "@/lib/seo/site";

export const metadata: Metadata = {
  metadataBase: getSiteOrigin() ?? undefined,
  robots: { index: false, follow: false },
  title: { default: "OpenRole", template: "%s · OpenRole" },
  description:
    "Direct-source job intelligence with visible observations and listing changes.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="font-sans antialiased">{children}</body>
    </html>
  );
}
