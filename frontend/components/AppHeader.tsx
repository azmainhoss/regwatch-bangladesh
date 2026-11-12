"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Search, UserRound } from "lucide-react";
import ThemeToggle from "./ThemeToggle";
import AccountModal from "./AccountModal";
import { AUTH_CHANGED_EVENT, AuthUser, fetchCurrentUser, getStoredUser } from "../services/api";

export const SEARCH_INPUT_ID = "circular-search";

function Mark() {
  // The wordmark's square: a folded page corner, drawn with two rectangles.
  return (
    <span aria-hidden className="relative grid h-7 w-7 place-items-center rounded-[5px] bg-accent text-accent-ink">
      <span className="absolute right-0 top-0 h-2.5 w-2.5 rounded-bl-[3px] bg-canvas/90" />
      <span className="mt-1 text-[13px] font-bold leading-none">R</span>
    </span>
  );
}

export default function AppHeader() {
  const pathname = usePathname();
  const router = useRouter();
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [accountOpen, setAccountOpen] = useState(false);

  useEffect(() => {
    // Show the cached session at once, then confirm it with the backend (GET /auth/me).
    setCurrentUser(getStoredUser());
    fetchCurrentUser()
      .then((u) => setCurrentUser(u))
      .catch(() => setCurrentUser(getStoredUser()));
    const onAuthChanged = () => setCurrentUser(getStoredUser());
    window.addEventListener(AUTH_CHANGED_EVENT, onAuthChanged);
    return () => window.removeEventListener(AUTH_CHANGED_EVENT, onAuthChanged);
  }, []);

  const focusSearch = () => {
    const input = document.getElementById(SEARCH_INPUT_ID) as HTMLInputElement | null;
    if (pathname === "/" && input) {
      input.focus();
      input.scrollIntoView({ behavior: "smooth", block: "center" });
    } else {
      router.push("/");
    }
  };

  const nav = [
    { href: "/", label: "Circulars", show: true },
    { href: "/admin", label: "Admin", show: !!currentUser?.is_superuser },
  ].filter((n) => n.show);

  const initials = currentUser?.full_name
    ?.split(/\s+/)
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <>
      <header className="sticky top-0 z-40 border-b border-line bg-canvas/90 backdrop-blur-md supports-[backdrop-filter]:bg-canvas/80">
        <div className="mx-auto flex h-14 max-w-[1480px] items-center gap-3 px-4 sm:gap-6 sm:px-6 lg:px-8">
          <Link href="/" className="flex shrink-0 items-center gap-2.5" aria-label="RegWatch home">
            <Mark />
            <span className="leading-tight">
              <span className="block text-[15px] font-bold tracking-tight text-ink">RegWatch</span>
              <span className="hidden text-2xs font-medium text-ink-3 sm:block">Bangladesh Bank circulars</span>
            </span>
          </Link>

          <nav className="flex items-center gap-1 text-[14px] font-semibold" aria-label="Main">
            {nav.map((item) => {
              const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={`relative rounded-control px-2.5 py-1.5 transition-colors ${active ? "text-ink" : "text-ink-3 hover:text-ink"}`}
                >
                  {item.label}
                  {active && (
                    <motion.span
                      layoutId="nav-underline"
                      className="absolute inset-x-2.5 -bottom-[11px] h-[2px] rounded-full bg-accent"
                      transition={{ type: "spring", stiffness: 500, damping: 40 }}
                    />
                  )}
                </Link>
              );
            })}
          </nav>

          <div className="ml-auto flex items-center gap-2">
            {pathname !== "/" && (
            <>
            <button
              type="button"
              onClick={focusSearch}
              className="hidden h-9 items-center gap-2 rounded-control border border-line bg-surface px-3 text-[13px] text-ink-3 transition-colors hover:border-line-strong hover:text-ink-2 md:flex md:w-56"
            >
              <Search className="h-4 w-4" strokeWidth={1.75} />
              <span>Search circulars</span>
            </button>
            <button
              type="button"
              onClick={focusSearch}
              aria-label="Search circulars"
              className="grid h-9 w-9 place-items-center rounded-control border border-line text-ink-2 hover:bg-sunken md:hidden"
            >
              <Search className="h-4 w-4" strokeWidth={1.75} />
            </button>
            </>
            )}

            <button
              type="button"
              onClick={() => setAccountOpen(true)}
              className="flex h-9 items-center gap-2 rounded-control border border-line px-1.5 text-[13px] font-semibold text-ink-2 transition-colors hover:border-line-strong hover:bg-sunken hover:text-ink sm:pr-3"
              title={currentUser ? `Signed in as ${currentUser.email}` : "Sign in"}
            >
              {currentUser ? (
                <>
                  <span className="grid h-6 w-6 place-items-center rounded-full bg-accent-soft text-2xs font-bold text-accent">
                    {initials || "U"}
                  </span>
                  <span className="hidden max-w-[160px] truncate sm:inline">{currentUser.full_name}</span>
                </>
              ) : (
                <>
                  <UserRound className="ml-1 h-4 w-4" strokeWidth={1.75} />
                  <span className="pr-1.5 sm:pr-0">Sign in</span>
                </>
              )}
            </button>

            <ThemeToggle />
          </div>
        </div>
      </header>

      <AccountModal
        isOpen={accountOpen}
        onClose={() => setAccountOpen(false)}
        currentUser={currentUser}
        onUserChange={setCurrentUser}
      />
    </>
  );
}
