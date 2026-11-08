"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ShieldCheck, User, Search, Settings } from "lucide-react";
import ThemeToggle from "./ThemeToggle";
import AccountModal from "./AccountModal";
import { AuthUser, ensureDefaultBankingSession, getStoredUser } from "../services/api";

export default function AppHeader() {
  const pathname = usePathname();
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [isAccountModalOpen, setIsAccountModalOpen] = useState(false);

  useEffect(() => {
    // Load existing session if present
    const stored = getStoredUser();
    if (stored) {
      setCurrentUser(stored);
    }
  }, []);

  const handleSearchClick = (e: React.MouseEvent) => {
    if (pathname === "/") {
      e.preventDefault();
      const searchInput = document.querySelector<HTMLInputElement>("input[placeholder*='Search']");
      if (searchInput) {
        searchInput.focus();
        searchInput.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }
  };

  return (
    <>
      <header className="border-b border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 bg-tealNavy-900/95 dark:bg-tealNavy-900/95 light:bg-white/95 backdrop-blur sticky top-0 z-50 transition-colors">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          {/* Brand identity */}
          <div className="flex items-center space-x-6">
            <Link href="/" className="flex items-center space-x-3 group">
              <div className="w-9 h-9 rounded-lg bg-tealNavy-800 border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 flex items-center justify-center text-turquoise group-hover:border-turquoise group-hover:shadow-[0_0_12px_rgba(45,212,191,0.3)] transition">
                <ShieldCheck className="w-5 h-5 text-turquoise" />
              </div>
              <div>
                <div className="flex items-center gap-1.5 font-semibold text-lg tracking-tight text-white dark:text-white light:text-tealNavy-950">
                  <span>RegWatch</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-tealNavy-800 dark:bg-tealNavy-800 light:bg-teal-50 text-turquoise dark:text-turquoise light:text-teal-700 font-mono border border-tealNavy-700 dark:border-tealNavy-700 light:border-teal-200 font-bold">
                    BD
                  </span>
                </div>
                <span className="text-[10px] text-slate-400 dark:text-slate-400 light:text-slate-500 block tracking-wider uppercase font-medium">
                  Bangladesh Regulatory Intelligence
                </span>
              </div>
            </Link>

            {/* Primary Navigation: Circulars, Search, Account */}
            <nav className="hidden md:flex items-center space-x-1 pl-4 border-l border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 text-sm font-medium">
              <Link
                href="/"
                className={`px-3.5 py-1.5 rounded-lg transition ${pathname === "/"
                    ? "bg-tealNavy-800 dark:bg-tealNavy-800 light:bg-teal-50 text-turquoise dark:text-turquoise light:text-teal-700 font-semibold border border-tealNavy-700 dark:border-tealNavy-700 light:border-teal-200"
                    : "text-slate-300 dark:text-slate-300 light:text-slate-600 hover:text-white dark:hover:text-white light:hover:text-tealNavy-950 hover:bg-tealNavy-850 dark:hover:bg-tealNavy-850 light:hover:bg-slate-100"
                  }`}
              >
                Circulars
              </Link>
              <button
                onClick={handleSearchClick}
                className="px-3.5 py-1.5 rounded-lg text-slate-300 dark:text-slate-300 light:text-slate-600 hover:text-white dark:hover:text-white light:hover:text-tealNavy-950 hover:bg-tealNavy-850 dark:hover:bg-tealNavy-850 light:hover:bg-slate-100 transition flex items-center gap-1.5"
              >
                <Search className="w-3.5 h-3.5 text-slate-400" />
                <span>Search</span>
              </button>
              <button
                onClick={() => setIsAccountModalOpen(true)}
                className="px-3.5 py-1.5 rounded-lg text-slate-300 dark:text-slate-300 light:text-slate-600 hover:text-white dark:hover:text-white light:hover:text-tealNavy-950 hover:bg-tealNavy-850 dark:hover:bg-tealNavy-850 light:hover:bg-slate-100 transition flex items-center gap-1.5"
              >
                <User className="w-3.5 h-3.5 text-turquoise" />
                <span>Account</span>
              </button>
              {currentUser?.is_superuser && (
                <Link
                  href="/admin"
                  className={`px-3 py-1.5 rounded-lg transition text-xs flex items-center gap-1 ${pathname === "/admin"
                      ? "bg-purple-950/80 text-purple-300 font-semibold border border-purple-800"
                      : "text-slate-400 hover:text-white hover:bg-tealNavy-850"
                    }`}
                  title="Administrative Management Console"
                >
                  <Settings className="w-3.5 h-3.5" />
                  <span>Admin</span>
                </Link>
              )}
            </nav>
          </div>

          {/* User & Theme Controls */}
          <div className="flex items-center space-x-3">
            {/* User Session Pill */}
            <button
              onClick={() => setIsAccountModalOpen(true)}
              className="flex items-center space-x-2 text-xs bg-tealNavy-850 dark:bg-tealNavy-850 light:bg-slate-100 border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 rounded-lg px-3 py-1.5 text-slate-200 dark:text-slate-200 light:text-tealNavy-950 hover:border-turquoise transition"
              title="Click to view account details or sign in"
            >
              {currentUser ? (
                <>
                  <div className="w-2 h-2 rounded-full bg-emerald-400"></div>
                  <span className="font-medium truncate max-w-[140px] sm:max-w-[200px]">
                    {currentUser.full_name}
                  </span>
                </>
              ) : (
                <>
                  <User className="w-3.5 h-3.5 text-turquoise" />
                  <span className="font-medium">Sign In</span>
                </>
              )}
            </button>

            {/* Theme Toggle */}
            <ThemeToggle />
          </div>
        </div>
      </header>

      {/* Account Modal */}
      <AccountModal
        isOpen={isAccountModalOpen}
        onClose={() => setIsAccountModalOpen(false)}
        currentUser={currentUser}
        onUserChange={setCurrentUser}
      />
    </>
  );
}
