import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "GitHub AI Agent — Dashboard",
  description: "Otonom GitHub AI Agent kontrol paneli",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="tr">
      <body>{children}</body>
    </html>
  );
}
