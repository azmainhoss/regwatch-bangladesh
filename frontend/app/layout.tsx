import type { Metadata, Viewport } from "next";
import { JetBrains_Mono, Newsreader, Noto_Sans_Bengali, Source_Sans_3 } from "next/font/google";
import "./globals.css";
import AppHeader from "../components/AppHeader";
import Providers from "../components/Providers";
import AuthGate from "../components/AuthGate";
import InstallApp from "../components/InstallApp";
import Analytics from "../components/Analytics";
import Link from "next/link";

const latin = Source_Sans_3({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  style: ["normal", "italic"],
  variable: "--font-latin",
  display: "swap",
});

const bangla = Noto_Sans_Bengali({
  subsets: ["bengali"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-bangla",
  display: "swap",
});

// Headline face for the home page.
const serif = Newsreader({
  subsets: ["latin"],
  weight: ["500", "600"],
  variable: "--font-serif",
  display: "swap",
});

const mono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL || "https://amarcircular.com"),
  title: "Bangladesh Bank Circulars, summarised (BRPD, FEPD, BFIU) | Amar Circular",
  description:
    "Every new Bangladesh Bank circular, summarised the day it is issued: what changed, what banks must do, deadlines, and the exact page in the original PDF. বাংলাদেশ ব্যাংকের সার্কুলার।",
  openGraph: {
    type: "website",
    siteName: "Amar Circular",
    url: "/",
    title: "Amar Circular: Bangladesh Bank circulars, summarised",
    description: "Every new Bangladesh Bank circular, summarised the day it is issued, with the page each point comes from.",
    locale: "en_BD",
    images: [{ url: "/brand/lockup-1200.png", width: 1200, height: 400, alt: "Amar Circular" }],
  },
  twitter: { card: "summary_large_image" },
  // Search Console / Bing Webmaster ownership tags, set on the server when the owner verifies the site.
  verification: {
    google: process.env.NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION || undefined,
    other: process.env.NEXT_PUBLIC_BING_SITE_VERIFICATION ? { "msvalidate.01": process.env.NEXT_PUBLIC_BING_SITE_VERIFICATION } : undefined,
  },
  applicationName: "Amar Circular",
  appleWebApp: { capable: true, title: "Amar Circular", statusBarStyle: "black-translucent" },
  icons: { icon: [{ url: "/icon.svg", type: "image/svg+xml" }, { url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" }], apple: "/icons/apple-touch-icon.png" },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f5f7f5" },
    { media: "(prefers-color-scheme: dark)", color: "#0e1311" },
  ],
};

// Every page links to the main list pages, so search engines find them from anywhere on the site.
const FOOTER_LINKS: [string, string][] = [
  ["/circulars", "Latest circulars"],
  ["/circulars/brpd", "BRPD circulars"],
  ["/circulars/fepd", "FEPD circulars"],
  ["/circulars/dos", "DOS circulars"],
  ["/circulars/bfiu", "BFIU circulars"],
  ["/circulars/psd", "PSD circulars"],
  ["/circulars/dfim", "DFIM circulars"],
  ["/circulars/topic/default-loans", "Loan rescheduling"],
  ["/circulars/topic/provision", "Loan classification"],
  ["/circulars/topic/forex", "Foreign exchange"],
  ["/circulars/topic/aml", "AML / KYC"],
  [`/circulars/${new Date().getFullYear()}`, `Circulars ${new Date().getFullYear()}`],
];

// Who runs the site and its search box, for search engines (Organization + WebSite with a search action).
const SITE = (process.env.NEXT_PUBLIC_SITE_URL || "https://amarcircular.com").replace(/\/+$/, "");
const SITE_JSON_LD = JSON.stringify({
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      "@id": `${SITE}/#org`,
      name: "Amar Circular",
      url: SITE,
      logo: `${SITE}/icons/icon-512.png`,
      description: "Bangladesh Bank circulars, summarised the day they are issued, with the page each point comes from.",
      areaServed: "BD",
    },
    {
      "@type": "WebSite",
      "@id": `${SITE}/#website`,
      name: "Amar Circular",
      alternateName: ["আমার সার্কুলার", "AmarCircular"],
      url: SITE,
      inLanguage: ["en", "bn"],
      publisher: { "@id": `${SITE}/#org` },
      potentialAction: {
        "@type": "SearchAction",
        target: { "@type": "EntryPoint", urlTemplate: `${SITE}/search?q={search_term_string}` },
        "query-input": "required name=search_term_string",
      },
    },
  ],
}).replace(/</g, "\\u003c");

// Runs before paint so a saved dark choice never flashes light first.
const themeScript = `try{if(localStorage.getItem('theme')==='dark'){document.documentElement.classList.add('dark');document.documentElement.style.colorScheme='dark'}}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning className={`${latin.variable} ${bangla.variable} ${mono.variable} ${serif.variable}`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: SITE_JSON_LD }} />
      </head>
      <body className="flex min-h-[100dvh] flex-col">
        <Providers>
          <AuthGate
            header={<AppHeader />}
            footer={
              <footer className="border-t border-line pb-[calc(56px+env(safe-area-inset-bottom))] sm:pb-0">
                <nav
                  aria-label="Circular lists"
                  className="mx-auto flex max-w-[1480px] flex-wrap gap-x-4 gap-y-1.5 px-4 pt-5 text-[13px] text-ink-2 sm:px-6 lg:px-8"
                >
                  {FOOTER_LINKS.map(([href, label]) => (
                    <Link key={href} href={href} className="hover:text-ink hover:underline">
                      {label}
                    </Link>
                  ))}
                </nav>
                <div className="mx-auto flex max-w-[1480px] flex-col gap-1 px-4 py-5 text-[13px] text-ink-3 sm:flex-row sm:items-center sm:justify-between sm:px-6 lg:px-8 !pb-2">
                  <span>Amar Circular. Every finding links back to the page it came from.</span>
                  <span>Source: Bangladesh Bank circulars</span>
                </div>
                <p className="mx-auto max-w-[1480px] px-4 pb-5 text-[13px] text-ink-3 sm:px-6 lg:px-8">
                  This is not an official reference. Please verify the original reference at your own responsibility before
                  making any decision.
                </p>
              </footer>
            }
          >
            {children}
          </AuthGate>
          <InstallApp />
          <Analytics />
        </Providers>
      </body>
    </html>
  );
}
