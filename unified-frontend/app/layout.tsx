import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "India Transition Lab",
  description: "Multi-sector decarbonisation modelling — NITI Aayog Vol.4",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
