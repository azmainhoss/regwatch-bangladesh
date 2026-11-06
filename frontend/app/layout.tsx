import type { Metadata } from "next";
import "./globals.css";
import AppHeader from "../components/AppHeader";

export const metadata: Metadata = {
  title: "RegWatch Bangladesh | Regulatory Intelligence & Compliance Platform",
  description: "Enterprise Bangladesh-first Regulatory Intelligence Platform for Banks, NBFIs, and Financial Institutions. Visual Direction 04 Deep Teal & Turquoise.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              try {
                var stored = localStorage.getItem('theme');
                if (stored === 'light') {
                  document.documentElement.classList.remove('dark');
                  document.documentElement.classList.add('light');
                } else {
                  document.documentElement.classList.remove('light');
                  document.documentElement.classList.add('dark');
                }
              } catch (e) {}
            `,
          }}
        />
      </head>
      <body className="bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-slate-50 text-slate-100 dark:text-slate-100 light:text-tealNavy-950 min-h-screen flex flex-col antialiased transition-colors">
        {/* Visual Direction 04 App Terminal Header */}
        <AppHeader />

        {/* Main Content Area */}
        <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {children}
        </main>

        {/* Financial Terminal Footer */}
        <footer className="border-t border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 bg-tealNavy-900 dark:bg-tealNavy-900 light:bg-white text-slate-400 dark:text-slate-400 light:text-slate-600 text-xs py-6 transition-colors">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-4">
            <div>
              2026 RegWatch Bangladesh. Grounded regulatory intelligence with strict page-level citation invariants.
            </div>
            <div className="flex items-center space-x-4 font-mono text-[11px] text-slate-400 dark:text-slate-400 light:text-slate-500">
              <span>Coverage: Bangladesh Bank (BRPD, DOS, SMESPD, FEPD, PSD)</span>
              <span>-</span>
              <span className="text-turquoise dark:text-turquoise light:text-teal-700">SHA-256 Verified Immutability</span>
            </div>
          </div>
        </footer>
      </body>
    </html>
  );
}
