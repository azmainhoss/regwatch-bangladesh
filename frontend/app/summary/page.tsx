"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Notice, SkeletonLine } from "@/components/ui";
import { fetchCurrentUser, fetchSummary, getStoredUser, type Summary } from "@/services/api";

const n = (x: number) => x.toLocaleString("en-US");
const pct = (a: number, b: number) => (b ? Math.round((a / b) * 100) : 0);
const fmtDay = (iso: string | null | undefined) =>
  iso ? new Date(iso + "T00:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short" }) : "";

const STATE: Record<string, { label: string; cls: string }> = {
  analysed: { label: "Analysed", cls: "bg-ok-soft text-ok" },
  added: { label: "Saved, analysis next", cls: "bg-info-soft text-info" },
  waiting: { label: "Downloads at next check", cls: "bg-warn-soft text-warn" },
};

function Bar({ value, total, cls }: { value: number; total: number; cls: string }) {
  return (
    <div className="h-2.5 w-full overflow-hidden rounded-full bg-sunken" role="progressbar" aria-valuenow={value} aria-valuemax={total}>
      <div className={`h-full rounded-full ${cls}`} style={{ width: `${pct(value, total)}%` }} />
    </div>
  );
}

export default function SummaryPage() {
  // Internal progress page: administrators only. Everyone else goes to the dashboard.
  const router = useRouter();
  const [allowed, setAllowed] = useState(false);
  useEffect(() => {
    if (getStoredUser()?.is_superuser) setAllowed(true);
    fetchCurrentUser()
      .then((u) => (u?.is_superuser ? setAllowed(true) : router.replace("/")))
      .catch(() => router.replace("/"));
  }, [router]);
  const [s, setS] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setS(await fetchSummary());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the summary.");
    }
  }, []);

  // Fresh on open, every minute, and when the tab comes back into view.
  useEffect(() => {
    if (!allowed) return;
    void load();
    const t = setInterval(load, 60_000);
    const onFocus = () => void load();
    window.addEventListener("focus", onFocus);
    return () => { clearInterval(t); window.removeEventListener("focus", onFocus); };
  }, [load, allowed]);

  const max = s ? Math.max(1, ...s.caught_per_day.map((d) => d.count)) : 1;

  if (!allowed) return null;
  return (
    <div className="mx-auto max-w-[1000px] space-y-5">
      <div>
        <h1 className="text-[22px] font-bold tracking-tight text-ink">Status</h1>
        <p className="mt-1 max-w-[70ch] text-sm text-ink-2">
          {s
            ? `${n(s.library_total)} Bangladesh Bank circulars from ${s.first_year} to ${fmtDay(s.last_date)} ${s.last_date?.slice(0, 4)}. ${n(s.caught_count)} new ones caught in the last ${s.caught_per_day.length} days.`
            : "Loading…"}
        </p>
      </div>

      {error && <Notice kind="error">{error}</Notice>}

      <section aria-label="Key numbers" className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {[
          { label: "Circulars saved", value: s ? n(s.library_total) : null, sub: s ? `since ${s.first_year}` : "" },
          { label: "New ones caught", value: s ? n(s.caught_count) : null, sub: s ? `last ${s.caught_per_day.length} days` : "" },
          { label: "Analysed", value: s ? n(s.target_analysed) : null, sub: s ? `of ${n(s.target_total)} in scope` : "" },
          { label: "Pages read", value: s ? `${pct(s.pages_read, s.pages_total)}%` : null, sub: s ? `${n(s.pages_read)} of ${n(s.pages_total)}` : "" },
        ].map((t) => (
          <div key={t.label} className="panel flex flex-col gap-1 p-4">
            <span className="text-2xs font-semibold uppercase tracking-wider text-ink-3">{t.label}</span>
            {t.value === null ? <SkeletonLine className="h-8 w-20" /> : <span className="text-3xl font-bold tabular-nums tracking-tight text-ink">{t.value}</span>}
            <span className="text-xs text-ink-2">{t.sub || " "}</span>
          </div>
        ))}
      </section>

      <section className="panel space-y-4 p-4">
        <h2 className="text-base font-semibold text-ink">Analysis progress</h2>
        {s ? (
          <div className="space-y-4 text-sm">
            <div className="grid grid-cols-1 gap-2 rounded-control bg-sunken p-3 sm:grid-cols-3">
              <div><span className="block text-2xs font-semibold uppercase tracking-wider text-ink-3">In scope</span><span className="text-lg font-bold tabular-nums">{n(s.target_total)}</span></div>
              <div><span className="block text-2xs font-semibold uppercase tracking-wider text-ink-3">Issued since {fmtDay(s.target_cutoff)} {s.target_cutoff.slice(0, 4)}</span><span className="text-lg font-bold tabular-nums">{n(s.target_recent)}</span><span className="ml-1 text-xs text-ink-2">the last 2 years, all types</span></div>
              <div><span className="block text-2xs font-semibold uppercase tracking-wider text-ink-3">Older Master Circulars</span><span className="text-lg font-bold tabular-nums">{n(s.target_older_master)}</span><span className="ml-1 text-xs text-ink-2">still the base rules</span></div>
            </div>
            <div className="space-y-1.5">
              <div className="flex justify-between gap-3"><span className="text-ink">Analysed (scheduled runs every 5 hours)</span><span className="shrink-0 font-semibold tabular-nums">{n(s.target_analysed)} / {n(s.target_total)}</span></div>
              <Bar value={s.target_analysed} total={s.target_total} cls="bg-accent" />
            </div>
            <div className="space-y-1.5">
              <div className="flex justify-between gap-3"><span className="text-ink">Checked: every quote matches its page</span><span className="shrink-0 font-semibold tabular-nums">{n(s.target_checked)} / {n(s.target_total)}</span></div>
              <Bar value={s.target_checked} total={s.target_total} cls="bg-ok" />
            </div>
            <div className="space-y-1.5">
              <div className="flex justify-between gap-3"><span className="text-ink">Pages with usable text, in the {n(s.target_total)} in scope</span><span className="shrink-0 font-semibold tabular-nums">{n(s.target_pages_read)} / {n(s.target_pages_total)}</span></div>
              <Bar value={s.target_pages_read} total={s.target_pages_total} cls="bg-info" />
              <p className="text-xs text-ink-2">
                {n(s.target_pages_total - s.target_pages_read)} pages in {n(s.target_circulars_with_unread)} circulars have no usable text yet (scans that failed to read, or broken old fonts). Those circulars wait and are analysed once their pages are read again.
              </p>
            </div>
          </div>
        ) : <SkeletonLine className="h-24 w-full" />}
      </section>

      <section className="panel space-y-3 p-4">
        <div>
          <h2 className="text-base font-semibold text-ink">New circulars caught, by day published</h2>
          <p className="text-xs text-ink-2">The website checker looks for new circulars every 10 minutes during office hours.</p>
        </div>
        {s ? (
          <div className="relative">
            {s.caught_per_day.every((d) => d.count === 0) && (
              <p className="absolute inset-x-0 top-10 text-center text-[13.5px] text-ink-3">No new circulars in these {s.caught_per_day.length} days.</p>
            )}
            <div className="flex h-32 items-end gap-1" role="img" aria-label="New circulars caught per day">
              {s.caught_per_day.map((d) => (
                <div key={d.day} className="flex h-full flex-1 flex-col items-center justify-end gap-1">
                  <span className="text-2xs tabular-nums text-ink-3">{d.count || ""}</span>
                  <div className="w-full rounded-t-sm bg-accent" style={{ height: `${(d.count / max) * 100}%`, minHeight: d.count ? 2 : 0 }} title={`${fmtDay(d.day)}: ${d.count}`} />
                </div>
              ))}
            </div>
            <div className="mt-1 flex gap-1 border-t border-line pt-1">
              {s.caught_per_day.map((d, i) => (
                <span key={d.day} className="flex-1 whitespace-nowrap text-center text-2xs text-ink-3">{i % 3 === 0 ? fmtDay(d.day) : ""}</span>
              ))}
            </div>
          </div>
        ) : <SkeletonLine className="h-32 w-full" />}
      </section>

      <section className="panel overflow-hidden">
        <h2 className="px-4 pt-4 text-base font-semibold text-ink">Latest new circulars</h2>
        <ul className="mt-2 divide-y divide-line">
          {s?.caught.slice(0, 12).map((c) => {
            const st = STATE[c.state] ?? STATE.added;
            const body = (
              <>
                <span className="w-14 shrink-0 text-xs tabular-nums text-ink-3">{fmtDay(c.published)}</span>
                <span className="min-w-0 flex-1 text-sm text-ink">{c.title}</span>
                <span className={`shrink-0 rounded-full px-2 py-0.5 text-2xs font-semibold ${st.cls}`}>{st.label}</span>
              </>
            );
            return (
              <li key={(c.reference ?? c.title) + c.published}>
                {c.document_id ? (
                  <Link href={`/circular/${c.document_id}`} className="flex items-start gap-3 px-4 py-2.5 hover:bg-sunken">{body}</Link>
                ) : (
                  <div className="flex items-start gap-3 px-4 py-2.5">{body}</div>
                )}
              </li>
            );
          })}
          {s && s.caught.length === 0 && <li className="px-4 py-3 text-sm text-ink-2">No new circulars in this period.</li>}
          {!s && <li className="px-4 py-3"><SkeletonLine className="h-16 w-full" /></li>}
        </ul>
      </section>
    </div>
  );
}
