import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Valence | Finance Research Terminal",
  description: "Institutional-grade equity valuation and investment memo execution for every investor.",
  icons: {
    icon: [
      { url: "/brand/valence-favicon.svg", type: "image/svg+xml" },
      { url: "/icon.svg", type: "image/svg+xml" },
    ],
    shortcut: "/brand/valence-favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
