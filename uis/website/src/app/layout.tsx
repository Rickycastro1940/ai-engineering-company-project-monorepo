import type { Metadata } from "next";
import type { ReactNode } from "react";
import "../styles/tokens.css";

export const metadata: Metadata = {
  title: "Brasaland — Grilled food, Colombia & Florida",
  description:
    "Brasaland — grilled food the same in Medellín and Miami. 14 restaurants across Colombia and Florida.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Outfit:wght@500;600;700&family=Source+Sans+3:ital,wght@0,400;0,600;1,400&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
