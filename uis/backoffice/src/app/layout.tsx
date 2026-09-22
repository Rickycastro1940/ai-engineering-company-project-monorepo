import type { Metadata } from "next";
import type { ReactNode } from "react";
import "../styles/backoffice.css";

export const metadata: Metadata = {
  title: "Brasaland Backoffice",
  description: "Brasaland Digital backoffice — internal operations entry for Colombia and Florida.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
