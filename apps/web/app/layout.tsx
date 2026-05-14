import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "trade — control plane",
  description: "Polymarket US × Kalshi autonomous trading dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
