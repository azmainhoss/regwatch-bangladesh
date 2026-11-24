"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { AUTH_CHANGED_EVENT, AuthUser, fetchCurrentUser, getStoredUser } from "@/services/api";
import { fetchFeedCounts, type FeedCounts } from "@/services/libraryApi";
import { useLists } from "@/services/listsStore";
import AccountModal from "@/components/AccountModal";
import DashboardAsk from "@/components/DashboardAsk";
import DashboardCards, { type Box } from "@/components/DashboardCards";

// The circular in the hero picture: a real point, its real quote, on page 1 of 2.
const HERO_DOC = "ce648d4f-0e8e-4cc7-b4d0-481bb64617cb";

const num = (n: number | undefined) => (n === undefined ? "–" : n.toLocaleString("en-US"));

/** amarcircular.com: what the site does, the four cards, and Ask. The library itself is at /dashboard. */
function Home() {
  const router = useRouter();
  const params = useSearchParams();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [accountOpen, setAccountOpen] = useState(false);
  const [counts, setCounts] = useState<FeedCounts | null>(null);
  const lists = useLists();

  // Old links (emails, alerts, saved bookmarks) used "/?doc=…" and "/?box=…": they belong to the dashboard now.
  const legacy = ["doc", "box", "page", "version"].some((k) => params.has(k));
  useEffect(() => {
    if (legacy) router.replace(`/dashboard?${params.toString()}`);
  }, [legacy, params, router]);

  useEffect(() => {
    setUser(getStoredUser());
    fetchCurrentUser()
      .then(setUser)
      .catch(() => setUser(getStoredUser()));
    const on = () => setUser(getStoredUser());
    window.addEventListener(AUTH_CHANGED_EVENT, on);
    return () => window.removeEventListener(AUTH_CHANGED_EVENT, on);
  }, []);

  useEffect(() => {
    fetchFeedCounts()
      .then(setCounts)
      .catch(() => undefined);
  }, [user?.id, lists.version]);

  if (legacy) return null;

  const later = lists.lists.find((l) => l.kind === "READ_LATER");
  const count = (b: Box) => (counts ? (b === "later" ? (later ? later.document_ids.length : counts.read_later) : counts[b]) : null);

  return (
    <div className="space-y-12 sm:space-y-16">
      <AccountModal isOpen={accountOpen} onClose={() => setAccountOpen(false)} currentUser={user} onUserChange={setUser} />

      {/* Hero */}
      <section className="flex flex-wrap items-center gap-x-14 gap-y-12 pt-4 sm:pt-10">
        <div className="flex min-w-0 flex-[1_1_460px] flex-col gap-6">
          <h1 className="font-serif text-[40px] font-medium leading-[1.06] tracking-[-0.01em] text-ink sm:text-[52px] lg:text-[58px]">
            Know what updates <span className="hero-hl px-1">came today</span>
          </h1>
          <p className="max-w-[540px] text-[17px] leading-[1.55] text-ink-2 sm:text-[19px]">
            Every new circular is notified on the day it’s issued, highlighting what has changed, what banks need to do, and exactly
            where to find it in the original document.
          </p>
          <div>
            <Link
              href="/dashboard"
              className="inline-flex min-h-[48px] items-center rounded-[10px] bg-accent px-6 py-3.5 text-[17px] font-semibold text-accent-ink transition-colors hover:bg-accent-hover"
            >
              Open the library — free
            </Link>
          </div>
          <dl className="mt-2 flex flex-wrap gap-x-10 gap-y-4">
            {[
              ["Circulars in the library", counts?.library],
              ["Issued this month", counts?.month],
              ["Points without a page cite", counts?.uncited_points],
            ].map(([label, value]) => (
              <div key={label as string}>
                <dt className="text-[13px] text-ink-3">{label}</dt>
                <dd className="mt-0.5 text-[26px] font-bold tabular-nums text-ink">{num(value as number | undefined)}</dd>
              </div>
            ))}
          </dl>
        </div>

        <figure
          className="relative m-0 flex min-w-0 flex-[1_1_520px] flex-col items-end"
          aria-label="A requirement from BRPD-1 Circular Letter No. 40 linked to the highlighted sentence on page 1 of the original circular"
        >
          <Link
            href={`/dashboard?doc=${HERO_DOC}`}
            className="relative z-[2] flex w-[92%] max-w-[480px] flex-col gap-2.5 self-start rounded-[14px] border border-line bg-surface px-[22px] pb-4 pt-5 shadow-pop transition-colors hover:border-accent/50"
          >
            <span className="flex flex-wrap items-center gap-2">
              <span className="text-[13px] font-semibold text-accent">BRPD-1 Circular Letter No. 40</span>
              <span className="rounded-full bg-accent-soft px-2 py-0.5 text-[12px] font-semibold text-accent">In force</span>
              <span className="rounded-full bg-warn-soft px-2 py-0.5 text-[12px] font-semibold text-warn">Checked</span>
            </span>
            <span className="flex items-baseline justify-between gap-3">
              <span className="text-[17px] font-bold leading-[1.3] text-ink">Borrowers with court stay orders are loan-eligible</span>
              <span className="whitespace-nowrap rounded border border-ink px-1.5 py-px text-[11px] font-bold uppercase tracking-[0.06em] text-ink">
                Mandatory
              </span>
            </span>
            <span className="text-[15px] leading-normal text-ink-2">
              Scheduled banks must treat these borrowers as eligible under the 15 stimulus schemes listed in Annexure ‘A’.
            </span>
            <span className="flex flex-wrap items-center gap-2.5 text-[13px] text-ink-3">
              <span className="inline-flex items-center gap-1.5 rounded-md border border-accent/30 bg-accent-soft px-2 py-1 font-semibold text-accent">
                <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
                  <path d="M3 2h7l3 3v9H3z" fill="none" stroke="currentColor" strokeWidth="1.5" />
                  <path d="M5.5 9l1.8 1.8L11 7" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
                </svg>
                Page 1
              </span>
              Applies to all scheduled banks
            </span>
          </Link>

          <svg
            width="120"
            height="90"
            viewBox="0 0 120 90"
            aria-hidden="true"
            className="pointer-events-none absolute left-[18%] top-[190px] z-[3] overflow-visible text-accent"
          >
            <path className="hero-wire" d="M8 4 C 8 50, 80 40, 96 86" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            <circle cx="8" cy="4" r="4" fill="currentColor" />
            <circle cx="96" cy="86" r="4" fill="currentColor" />
          </svg>

          <div className="relative z-[1] -mt-7 flex w-[88%] max-w-[470px] flex-col gap-[9px] rounded-md border border-line bg-surface px-[30px] pb-[26px] pt-[52px] shadow-pop">
            <div className="flex justify-between text-[11px] text-ink-3">
              <span>Original PDF · bb.org.bd</span>
              <span>Page 1 of 2</span>
            </div>
            <div className="my-1.5 h-[7px] w-[62%] self-center rounded-[3px] bg-line" />
            <div className="h-[7px] w-full rounded-[3px] bg-sunken" />
            <div className="h-[7px] w-[94%] rounded-[3px] bg-sunken" />
            <p lang="bn" className="my-0.5 font-bangla text-[13.5px] leading-[1.75] text-ink">
              <span className="hero-hl py-0.5 shadow-[0_0_0_1px_rgb(var(--marker-edge))]">
                … উক্ত ঋণগ্রহীতাগণ সংযোজনী ‘ক’ এ উল্লেখিত স্কিমসমূহের আওতায় ঋণ প্রাপ্তির জন্য যোগ্য মর্মে বিবেচিত হবেন।
              </span>
            </p>
            <div className="h-[7px] w-[97%] rounded-[3px] bg-sunken" />
            <div className="h-[7px] w-[72%] rounded-[3px] bg-sunken" />
            <div className="mt-3 h-[7px] w-[38%] self-end rounded-[3px] bg-sunken" />
          </div>
        </figure>
      </section>

      {/* The same four cards as the dashboard; each opens the dashboard with that filter on. */}
      <section aria-label="Circulars by period" className="space-y-4">
        <DashboardCards
          count={count}
          signedIn={!!user}
          onPick={(id) => {
            if (id === "later" && !user) return setAccountOpen(true);
            router.push(`/dashboard?box=${id}`);
          }}
        />
        <DashboardAsk signedIn={!!user} onSignIn={() => setAccountOpen(true)} />
      </section>
    </div>
  );
}

export default function HomePage() {
  return (
    <Suspense fallback={null}>
      <Home />
    </Suspense>
  );
}
