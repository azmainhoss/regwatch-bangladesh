import type { Metadata, Viewport } from "next";
import { JetBrains_Mono, Noto_Sans_Bengali, Source_Sans_3 } from "next/font/google";
import "./globals.css";
import AppHeader from "../components/AppHeader";
import Providers from "../components/Providers";

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

const mono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "RegWatch Bangladesh",
  description: "Bangladesh Bank circulars with page-cited analysis for bank compliance teams.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f5f7f5" },
    { media: "(prefers-color-scheme: dark)", color: "#0e1311" },
  ],
};

// Runs before paint so a saved dark choice never flashes light first.
const themeScript = `try{if(localStorage.getItem('theme')==='dark'){document.documentElement.classList.add('dark');document.documentElement.style.colorScheme='dark'}}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning className={`${latin.variable} ${bangla.variable} ${mono.variable}`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="flex min-h-[100dvh] flex-col">
        <Providers>
          <AppHeader />
          <main className="mx-auto w-full max-w-[1480px] flex-1 px-4 py-6 sm:px-6 lg:px-8">{children}</main>
          <footer className="border-t border-line">
            <div className="mx-auto flex max-w-[1480px] flex-col gap-1 px-4 py-5 text-[13px] text-ink-3 sm:flex-row sm:items-center sm:justify-between sm:px-6 lg:px-8">
              <span>RegWatch Bangladesh. Every finding links back to the page it came from.</span>
              <span>Source: Bangladesh Bank circulars</span>
            </div>
          </footer>
        </Providers>
      </body>
    </html>
  );
}
