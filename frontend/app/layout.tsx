import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "RegWatch Bangladesh | Regulatory Intelligence & Compliance Platform",
  description: "Enterprise Bangladesh-first Regulatory Intelligence Platform for Banks, NBFIs, and Financial Institutions.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-slate-950 text-slate-100 min-h-screen flex flex-col antialiased">
        {/* Top Financial Intelligence Terminal Bar */}
        <header className="border-b border-slate-800 bg-slate-900/90 backdrop-blur sticky top-0 z-50">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
            <div className="flex items-center space-x-6">
              <Link href="/" className="flex items-center space-x-3 group">
                <div className="w-9 h-9 rounded bg-brand-600 flex items-center justify-center font-bold text-white shadow-md shadow-brand-500/20 group-hover:bg-brand-500 transition">
                  RW
                </div>
                <div>
                  <span className="font-semibold text-lg tracking-tight text-white flex items-center gap-1.5">
                    RegWatch <span className="text-xs px-1.5 py-0.5 rounded bg-brand-900 text-brand-300 font-mono border border-brand-700/50">BD</span>
                  </span>
                  <span className="text-[10px] text-slate-400 block tracking-wider uppercase font-medium">Bangladesh Regulatory Intelligence</span>
                </div>
              </Link>

              <nav className="hidden md:flex items-center space-x-1 pl-4 border-l border-slate-800 text-sm font-medium">
                <Link
                  href="/"
                  className="px-3 py-1.5 rounded-md text-slate-200 hover:text-white hover:bg-slate-800 transition"
                >
                  Professional Feed
                </Link>
                <Link
                  href="/admin"
                  className="px-3 py-1.5 rounded-md text-slate-400 hover:text-white hover:bg-slate-800 transition"
                >
                  Admin Console & Ingestion
                </Link>
              </nav>
            </div>

            <div className="flex items-center space-x-4">
              <div className="hidden sm:flex items-center space-x-2 text-xs bg-slate-800/80 border border-slate-700/60 rounded-full px-3 py-1">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                <span className="text-slate-300 font-mono">BB Portal Active</span>
              </div>
              <div className="text-xs font-mono text-slate-400 border border-slate-800 rounded px-2.5 py-1 bg-slate-900">
                v1.0.0-PROD
              </div>
            </div>
          </div>
        </header>

        {/* Main Content Area */}
        <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {children}
        </main>

        {/* Financial Terminal Footer */}
        <footer className="border-t border-slate-900 bg-slate-950 text-slate-500 text-xs py-6">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-4">
            <div>
              © 2026 RegWatch Bangladesh. Grounded regulatory intelligence with strict page-level citation invariants.
            </div>
            <div className="flex items-center space-x-4 font-mono text-[11px]">
              <span>Coverage: Bangladesh Bank (BRPD, DOS, FEPD, PSD)</span>
              <span>•</span>
              <span>SHA-256 Verified Immutability</span>
            </div>
          </div>
        </footer>
      </body>
    </html>
  );
}
