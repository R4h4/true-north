import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "True North — Governed BI",
  description: "Ask business questions; every answer is governed by the tn contract",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
