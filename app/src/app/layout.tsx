import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PolicyBench, by PolicyEngine",
  description:
    "Benchmarking no-tools household-level policy calculation across frontier models.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
