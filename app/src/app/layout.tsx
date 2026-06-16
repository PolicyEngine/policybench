import type { Metadata } from "next";
import "./globals.css";

const SITE_URL = "https://policybench.org";
const SITE_TITLE = "PolicyBench, by PolicyEngine";
const SITE_DESCRIPTION =
  "How accurately frontier AI models estimate US tax and benefit " +
  "amounts, scored against PolicyEngine reference outputs.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: SITE_TITLE,
    template: "%s — PolicyBench",
  },
  description: SITE_DESCRIPTION,
  alternates: {
    canonical: "/",
  },
  openGraph: {
    type: "website",
    url: SITE_URL,
    siteName: "PolicyBench",
    title: SITE_TITLE,
    description: SITE_DESCRIPTION,
    images: [
      {
        url: "/og-image.png",
        width: 1200,
        height: 630,
        alt: "PolicyBench — an LLM benchmark for tax and benefit calculation",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: SITE_TITLE,
    description: SITE_DESCRIPTION,
    images: ["/og-image.png"],
  },
  icons: {
    icon: [
      {
        url: "/assets/policyengine-mark.svg",
        type: "image/svg+xml",
      },
    ],
  },
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
