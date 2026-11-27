"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/services/api";

/** "Only a few need you now": this year's circulars as dots on a relevance × urgency grid, per institution type. */

type Grid = { year: number; library: number; circulars: C[] };
type C = { id: string; path?: string | null; ref?: string | null; title: string; published?: string | null; ents: string[]; mand: number; deadline?: string | null };
type Profile = { k: string; n: string; a: string; spec: string[]; gen: string[]; adj: string[] };

const PROFILES: Profile[] = [
  { k: "conv", n: "Conventional bank", a: "a conventional bank", spec: ["SCHEDULED_BANK"], gen: [], adj: ["AUTHORIZED_DEALER", "ISLAMIC_BANK"] },
  { k: "ad", n: "AD bank", a: "an AD bank", spec: ["AUTHORIZED_DEALER"], gen: ["SCHEDULED_BANK"], adj: ["OFFSHORE_BANKING_UNIT", "MONEY_CHANGER", "ISLAMIC_BANK"] },
  { k: "isl", n: "Islamic bank", a: "an Islamic bank", spec: ["ISLAMIC_BANK"], gen: ["SCHEDULED_BANK"], adj: ["AUTHORIZED_DEALER"] },
  { k: "nbfi", n: "NBFI", a: "an NBFI", spec: ["NBFI"], gen: [], adj: ["SCHEDULED_BANK"] },
  { k: "mfs", n: "MFS / payments", a: "an MFS or payment provider", spec: ["MOBILE_FINANCIAL_SERVICE", "PAYMENT_SERVICE_PROVIDER"], gen: [], adj: ["SCHEDULED_BANK"] },
];
const COLS = ["Other sectors", "Related", "Applies broadly", "Named for you"];
const ROWS = ["HIGH", "MEDIUM", "LOW"];
const LABEL: Record<string, string> = {
  SCHEDULED_BANK: "all scheduled banks", AUTHORIZED_DEALER: "authorised dealers (AD branches)", NBFI: "finance companies (NBFIs)",
  ISLAMIC_BANK: "Islamic banks", MOBILE_FINANCIAL_SERVICE: "mobile financial services", PAYMENT_SERVICE_PROVIDER: "payment service providers",
  OFFSHORE_BANKING_UNIT: "offshore banking units", MONEY_CHANGER: "money changers", FOREIGN_BANK: "foreign banks", STATE_OWNED_BANK: "state-owned banks",
  EXCHANGE_HOUSE: "exchange houses", MICROFINANCE_INSTITUTION: "microfinance institutions", SPECIALIZED_BANK: "specialised banks",
};
const lab = (e: string) => LABEL[e] || e.toLowerCase().replace(/_/g, " ");
const list = (xs: string[]) => (xs.length < 2 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`);

function todayDhaka() {
  return new Date(Date.now() + 6 * 3600e3).toISOString().slice(0, 10);
}
function col(d: C, p: Profile) {
  const has = (a: string[]) => a.some((e) => d.ents.includes(e));
  return has(p.spec) ? 3 : has(p.gen) ? 2 : has(p.adj) ? 1 : 0;
}
function row(d: C, today: string) {
  if (d.mand && d.deadline && d.deadline >= today) return 0;
  return d.mand ? 1 : 2;
}
function rnd(s: string) {
  let h = 2166136261;
  for (const c of s) h = Math.imul(h ^ c.charCodeAt(0), 16777619);
  return () => {
    h = Math.imul(h ^ (h >>> 15), 2246822507);
    h ^= h >>> 13;
    return (h >>> 0) / 4294967296;
  };
}
const fmt = (d?: string | null) => (d ? new Date(d).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) : "");

export default function AppliesGrid() {
  const [data, setData] = useState<Grid | null>(null);
  const [prof, setProf] = useState(PROFILES[0]);
  const [sel, setSel] = useState<string | null>(null);
  const today = todayDhaka();

  useEffect(() => {
    apiFetch("/public/grid").then((r) => (r.ok ? r.json() : null)).then(setData).catch(() => undefined);
  }, []);

  const placed = useMemo(() => {
    const g: C[][][] = ROWS.map(() => COLS.map(() => []));
    for (const d of data?.circulars || []) g[row(d, today)][col(d, prof)].push(d);
    return g;
  }, [data, prof, today]);

  const hot = placed[0][3];
  const fallback = hot.find((d) => d.ref?.startsWith("FEPD-2 Circular Letter No. 03")) || hot[0] || placed[1][3][0] || data?.circulars[0];
  const cur = data?.circulars.find((d) => d.id === sel) || fallback;

  return (
    <section aria-labelledby="hx-grid-h" className="flex flex-col gap-6">
      <div>
        <div className="hx-eyebrow">{data ? `${data.year} so far · ${data.circulars.length} Bangladesh Bank circulars` : "This year so far"}</div>
        <h2 id="hx-grid-h" className="hx-h2 mt-6">Only a few need you now.</h2>
        <p className="hx-lead mt-3">Every circular is read for who it applies to and how urgent it is. Pick your institution type and watch the year sort itself.</p>
      </div>

      <div className="hx-switch self-start" role="group" aria-label="Institution type">
        {PROFILES.map((p) => (
          <button key={p.k} type="button" className={p.k === prof.k ? "on" : ""} onClick={() => { setProf(p); setSel(null); }}>
            {p.n}
          </button>
        ))}
      </div>

      <div className="hx-stage">
        <div>
          <div className="hx-grid" role="img" aria-label={`This year's circulars sorted for ${prof.a}: ${hot.length} apply now.`}>
            {ROWS.map((r, ri) => [
              <div key={`y${ri}`} className="hx-ylab">{r}</div>,
              ...COLS.map((_, ci) => {
                const items = placed[ri][ci];
                const isHot = ri === 0 && ci === 3;
                return (
                  <div key={`${ri}-${ci}`} className={`hx-cell ${isHot ? "hot" : ci >= 2 ? "warm" : ""}`}>
                    <span className="hx-cnt">{items.length}</span>
                    {isHot && <div className="hx-big">{items.length}<small>apply now</small></div>}
                    {items.map((d) => {
                      const rr = rnd(d.id + (isHot ? "h" : ""));
                      const top0 = isHot ? 58 : 14;
                      return (
                        <button
                          key={d.id}
                          type="button"
                          aria-label={d.ref || d.title}
                          className={`hx-dot ${isHot ? "now" : ci >= 2 ? "rev" : "set"} ${cur?.id === d.id ? "sel" : ""}`}
                          style={{ left: `${10 + rr() * 80}%`, top: `${top0 + rr() * (88 - top0)}%` }}
                          onMouseEnter={() => setSel(d.id)}
                          onFocus={() => setSel(d.id)}
                          onClick={() => setSel(d.id)}
                        />
                      );
                    })}
                  </div>
                );
              }),
            ])}
            <div />
            {COLS.map((c) => <div key={c} className="hx-xlab">{c}</div>)}
          </div>
          <div className="hx-legend">
            <span className="flex items-center gap-2"><i className="inline-block h-1.5 w-1.5 rounded-full bg-ink-3/60" />Not for you</span>
            <span className="flex items-center gap-2"><i className="inline-block h-2.5 w-2.5 rounded-full border-2 border-[#d9a514]" />Worth a look</span>
            <span className="flex items-center gap-2"><i className="inline-block h-3 w-3 rounded-full bg-[#225E48] dark:bg-accent" />Applies now</span>
          </div>
        </div>
        {cur ? <Card d={cur} prof={prof} today={today} /> : <div className="hx-card h-[320px] animate-pulse" />}
      </div>
    </section>
  );
}

function Card({ d, prof, today }: { d: C; prof: Profile; today: string }) {
  const r = row(d, today);
  const c = col(d, prof);
  const mine = d.ents.filter((e) => prof.spec.includes(e) || prof.gen.includes(e));
  const who =
    c >= 2
      ? `Applies to ${list(mine.map(lab))}, which covers ${prof.a}.`
      : c === 1
        ? `Addressed to ${list(d.ents.map(lab))}: related to ${prof.a}, worth a look.`
        : `Addressed to ${d.ents.length ? list(d.ents.map(lab)) : "other institutions"}. Not for ${prof.a}.`;
  const days = d.deadline ? Math.round((+new Date(d.deadline) - +new Date(today)) / 864e5) : null;
  const urg = [["HIGH", "bg-[#c0392b] text-white"], ["MEDIUM", "bg-[#f1d68a] text-[#5a4300]"], ["LOW", "bg-sunken text-ink-2"]][r];
  return (
    <div className="hx-card">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`hx-pill ${urg[1]}`}>{urg[0]}</span>
        {d.ents.length > 0 && <span className="hx-pill border border-line text-accent">✓ Ready</span>}
      </div>
      <div className="hx-mono mt-4 text-[13px] font-semibold text-accent">{d.ref}</div>
      <h3 className="mb-3 mt-1 text-[19px] font-bold leading-snug text-ink">{d.title}</h3>
      <div className="hx-eyebrow mt-3" style={{ color: "rgb(var(--ink-3))" }}>Who it applies to</div>
      <p className="mt-1.5 text-[15px] leading-relaxed text-ink-2">{who}</p>
      <div className="hx-eyebrow mt-3" style={{ color: "rgb(var(--ink-3))" }}>What banks must do</div>
      <p className="mt-1.5 text-[15px] leading-relaxed text-ink-2">
        {d.mand ? `${d.mand} requirement${d.mand > 1 ? "s" : ""}, each linked to its page in the original.` : "Information only: no new requirement."}
      </p>
      <div className="mt-4 flex items-center justify-between border-t border-line pt-3 text-[14px]">
        <span className="text-ink-3">{fmt(d.published)}</span>
        {d.deadline ? (
          <span className="hx-mono font-semibold text-ink">
            Due {fmt(d.deadline)}
            {days !== null && days >= 0 && <span className="ml-1.5 rounded-md bg-sunken px-1.5 py-0.5 text-[12px]">{days}d</span>}
          </span>
        ) : (
          <span className="text-ink-3">No deadline</span>
        )}
      </div>
      <div className="mt-4 flex gap-2">
        <Link href={d.path || `/dashboard?doc=${d.id}`} className="flex-1 rounded-control border border-line py-2.5 text-center text-[14px] font-semibold text-ink hover:bg-sunken">
          Open circular
        </Link>
        <Link href={`/dashboard?doc=${d.id}`} className="btn-primary flex-1 justify-center py-2.5 text-center text-[14px]">
          Assign in workspace
        </Link>
      </div>
    </div>
  );
}
