import type { Metadata } from "next";
import Script from "next/script";
import "./globals.css";

const GA_MEASUREMENT_ID = "G-2YHG89FY0N";
const TOOL_NAME = "policybench";

const ANALYTICS_INLINE = `
window.dataLayer = window.dataLayer || [];
function gtag(){dataLayer.push(arguments);}
gtag('js', new Date());
gtag('config', '${GA_MEASUREMENT_ID}', { tool_name: '${TOOL_NAME}' });
`;

const SCROLL_INLINE = `
(function() {
  var TOOL_NAME = '${TOOL_NAME}';
  if (typeof window === 'undefined' || !window.gtag) return;

  var scrollFired = {};
  window.addEventListener('scroll', function() {
    var docHeight = document.documentElement.scrollHeight - window.innerHeight;
    if (docHeight <= 0) return;
    var pct = Math.floor((window.scrollY / docHeight) * 100);
    [25, 50, 75, 100].forEach(function(m) {
      if (pct >= m && !scrollFired[m]) {
        scrollFired[m] = true;
        window.gtag('event', 'scroll_depth', { percent: m, tool_name: TOOL_NAME });
      }
    });
  }, { passive: true });

  [30, 60, 120, 300].forEach(function(sec) {
    setTimeout(function() {
      if (document.visibilityState !== 'hidden') {
        window.gtag('event', 'time_on_tool', { seconds: sec, tool_name: TOOL_NAME });
      }
    }, sec * 1000);
  });

  document.addEventListener('click', function(e) {
    var link = e.target && e.target.closest ? e.target.closest('a') : null;
    if (!link || !link.href) return;
    try {
      var url = new URL(link.href, window.location.origin);
      if (url.hostname && url.hostname !== window.location.hostname) {
        window.gtag('event', 'outbound_click', {
          url: link.href,
          target_hostname: url.hostname,
          tool_name: TOOL_NAME
        });
      }
    } catch (err) {}
  });
})();
`;

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
        url: "/og-image.png?v=20260616",
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
    images: ["/og-image.png?v=20260616"],
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
        <Script
          src={`https://www.googletagmanager.com/gtag/js?id=${GA_MEASUREMENT_ID}`}
          strategy="afterInteractive"
        />
        <Script id="ga-init" strategy="afterInteractive">
          {ANALYTICS_INLINE}
        </Script>
        <Script id="scroll-tracking" strategy="afterInteractive">
          {SCROLL_INLINE}
        </Script>
      </body>
    </html>
  );
}
