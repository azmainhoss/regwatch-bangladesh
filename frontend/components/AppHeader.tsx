"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Activity, Briefcase, LayoutDashboard, Search, Shield, UserRound } from "lucide-react";
import ThemeToggle from "./ThemeToggle";
import AccountModal from "./AccountModal";
import BellButton from "./alerts/BellButton";
import { startAlertsSync } from "../services/alertsStore";
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
  // The header only mounts after the sign-in gate has read the saved user, so it can show that user at once (no "Sign in" flash).
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(() => (typeof window !== "undefined" ? getStoredUser() : null));
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

  // Alerts: poll while someone is signed in, and load the first page and the settings in the background.
  const signedInId = currentUser?.id ?? null;
  useEffect(() => {
    if (!signedInId) return;
    return startAlertsSync();
  }, [signedInId]);

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
    { href: "/", label: "Dashboard", Icon: LayoutDashboard, show: true },
    { href: "/search", label: "Search", Icon: Search, show: true },
    { href: "/workspace", label: "Workspace", Icon: Briefcase, show: !!currentUser },
    { href: "/admin", label: "Admin", Icon: Shield, show: !!currentUser?.is_superuser },
    { href: "/summary", label: "Status", Icon: Activity, show: !!currentUser?.is_superuser },
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
        <div className="mx-auto flex h-14 max-w-[1480px] items-center gap-2 px-4 sm:gap-6 sm:px-6 lg:px-8">
          <Link href="/" className="flex min-h-[44px] shrink-0 items-center gap-2.5" aria-label="RegWatch home">
            <Mark />
            <span className="hidden leading-tight sm:block">
              <span className="block text-[15px] font-bold tracking-tight text-ink">RegWatch</span>
              <span className="hidden text-2xs font-medium text-ink-3 sm:block">Bangladesh Bank circulars</span>
            </span>
          </Link>

          <nav className="hidden min-w-0 items-center gap-1 text-[14px] font-semibold sm:flex" aria-label="Main">
            {nav.map((item) => {
              const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={`relative flex min-h-[44px] items-center rounded-control px-2 transition-colors sm:min-h-0 sm:px-2.5 sm:py-1.5 ${active ? "text-ink" : "text-ink-3 hover:text-ink"}`}
                >
                  {item.label}
                  {active && (
                    <motion.span
                      layoutId="nav-underline"
                      className="absolute inset-x-2 bottom-0 h-[2px] rounded-full bg-accent sm:inset-x-2.5 sm:-bottom-[11px]"
                      transition={{ type: "spring", stiffness: 500, damping: 40 }}
                    />
                  )}
                </Link>
              );
            })}
          </nav>

          {/* Phones: the free space in the bar is a search field that opens the Search screen. */}
          {pathname !== "/search" && (
            <Link
              href="/search"
              className="flex h-10 min-w-0 flex-1 items-center gap-2 rounded-control border border-line bg-surface px-3 text-[14px] text-ink-3 sm:hidden"
            >
              <Search className="h-4 w-4 shrink-0" strokeWidth={1.75} />
              <span className="truncate">Search circulars</span>
            </Link>
          )}

          <div className="ml-auto flex shrink-0 items-center gap-2">
            {pathname !== "/" && pathname !== "/search" && (
            <>
            <button
              type="button"
              onClick={focusSearch}
              className="hidden h-9 items-center gap-2 rounded-control border border-line bg-surface px-3 text-[13px] text-ink-3 transition-colors hover:border-line-strong hover:text-ink-2 xl:flex xl:w-56"
            >
              <Search className="h-4 w-4" strokeWidth={1.75} />
              <span>Search circulars</span>
            </button>
            <button
              type="button"
              onClick={focusSearch}
              aria-label="Search circulars"
              className="hidden h-9 w-9 place-items-center rounded-control border border-line text-ink-2 hover:bg-sunken sm:grid xl:hidden"
            >
              <Search className="h-4 w-4" strokeWidth={1.75} />
            </button>
            </>
            )}

            {currentUser && <BellButton />}

            <button
              type="button"
              onClick={() => setAccountOpen(true)}
              className="flex h-11 shrink-0 items-center gap-2 whitespace-nowrap rounded-control border border-line px-1.5 sm:h-9 text-[13px] font-semibold text-ink-2 transition-colors hover:border-line-strong hover:bg-sunken hover:text-ink sm:pr-3"
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

      {/* Phones: the main sections as a bar at the bottom, in thumb reach. */}
      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-canvas/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-md sm:hidden"
      >
        <div className="flex items-stretch justify-around">
          {nav.map(({ href, label, Icon }) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={`flex min-h-[56px] flex-1 flex-col items-center justify-center gap-0.5 text-[11.5px] font-semibold transition-colors ${
                  active ? "text-accent" : "text-ink-3 active:text-ink"
                }`}
              >
                <Icon className="h-5 w-5" strokeWidth={active ? 2.2 : 1.75} aria-hidden />
                {label}
              </Link>
            );
          })}
        </div>
      </nav>

      <AccountModal
        isOpen={accountOpen}
        onClose={() => setAccountOpen(false)}
        currentUser={currentUser}
        onUserChange={setCurrentUser}
      />
    </>
  );
}
