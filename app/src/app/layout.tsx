import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "PolicyBench, by PolicyEngine",
    template: "%s — PolicyBench",
  },
  description:
    "Benchmarking no-tools policy calculation across frontier models.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">
        <a href="#main" className="skip-to-content">
          Skip to main content
        </a>
        {children}
      </body>
    </html>
  );
}
