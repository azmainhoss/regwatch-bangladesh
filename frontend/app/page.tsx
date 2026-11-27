"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AUTH_CHANGED_EVENT, AuthUser, fetchCurrentUser, getStoredUser } from "@/services/api";
import AccountModal from "@/components/AccountModal";
import DashboardCards, { type Box } from "@/components/DashboardCards";
import { fetchFeedCounts, type FeedCounts } from "@/services/libraryApi";
import { useLists } from "@/services/listsStore";
import AppliesGrid from "@/components/home/AppliesGrid";
import HowItWorks from "@/components/home/HowItWorks";
import TeamBand from "@/components/home/TeamBand";
import FeatureSplits from "@/components/home/FeatureSplits";
import Reveal from "@/components/home/Reveal";
import HeroDots from "@/components/home/HeroDots";
import "@/components/home/home.css";

/** amarcircular.com: what the site does, the four cards, and Ask. The library itself is at /dashboard. */
export default function HomePage() {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [accountOpen, setAccountOpen] = useState(false);
  const [counts, setCounts] = useState<FeedCounts | null>(null);
  const lists = useLists();

  // Old links (emails, alerts, saved bookmarks) used "/?doc=…" and "/?box=…": they belong to the dashboard now.
  // Read in an effect (not useSearchParams) so the page itself still renders on the server for search engines.
  const [legacy, setLegacy] = useState(false);
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (["doc", "box", "page", "version"].some((k) => params.has(k))) {
      setLegacy(true);
      router.replace(`/dashboard?${params.toString()}`);
    }
  }, [router]);

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
    fetchFeedCounts().then(setCounts).catch(() => undefined);
  }, [user?.id, lists.version]);
  // Live numbers: re-read every 5 minutes while the page is visible.
  useEffect(() => {
    const t = window.setInterval(() => {
      if (document.visibilityState === "visible") fetchFeedCounts().then(setCounts).catch(() => undefined);
    }, 5 * 60 * 1000);
    return () => window.clearInterval(t);
  }, []);

  // Snap scrolling between sections, only while the home page is open.
  useEffect(() => {
    document.documentElement.classList.add("hx-snap");
    return () => document.documentElement.classList.remove("hx-snap");
  }, []);

  if (legacy) return null;

  const later = lists.lists.find((l) => l.kind === "READ_LATER");
  // Each card opens the dashboard with that filter on.
  const pick = (id: Box) => {
    if (id === "later" && !user) return setAccountOpen(true);
    router.push(`/dashboard?box=${id}`);
  };
  const count = (b: Box) => (counts ? (b === "later" ? (later ? later.document_ids.length : counts.read_later) : counts[b]) : null);

  // Each section fills the screen, so one never shows the edge of the next (owner, 2026-11-28).
  return (
    <div className="pb-10">
      <AccountModal isOpen={accountOpen} onClose={() => setAccountOpen(false)} currentUser={user} onUserChange={setUser} />

      {/* Hero */}
      <section className="hx-screen hx-hero relative">
        <HeroDots />
        <div className="relative flex flex-col gap-7">
          <span className="text-[15px] font-semibold text-accent sm:text-[17px]">Bangladesh Bank circulars, summarised</span>
          <h1 className="font-serif text-[52px] font-medium leading-[0.98] tracking-[-0.025em] text-ink sm:text-[84px] lg:text-[112px]">
            Grab the updates <span className="hero-hl px-1">first!</span>
          </h1>
          <p className="max-w-[820px] text-[18px] leading-[1.55] text-ink-2 sm:text-[23px]">
            Every new Bangladesh Bank circular is notified on the day it’s issued, highlighting what has changed, what banks need to do, and exactly
            where to find it in the original document.
          </p>
          <div className="mt-4">
            <DashboardCards total={counts ? counts.library ?? null : null} onAll={() => router.push("/dashboard")} count={count} signedIn={!!user} onPick={pick} noLater />
          </div>
        </div>
      </section>

      <section className="hx-screen"><AppliesGrid /></section>
      <section className="hx-screen hx-reveal"><HowItWorks /></section>
      <section className="hx-screen hx-reveal"><TeamBand /></section>
      <FeatureSplits />
      <Reveal />
    </div>
  );
}
