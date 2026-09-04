import type { Metadata } from "next";
import "./globals.css";
import WarmBackends from "./WarmBackends";

export const metadata: Metadata = {
  title: "India Transition Lab",
  description: "Multi-sector decarbonisation modelling — NITI Aayog Vol.4",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased">
        {/* Invisible — wakes all 5 Railway backends on first page load */}
        <WarmBackends />
        {children}
      </body>
    </html>
  );
}
