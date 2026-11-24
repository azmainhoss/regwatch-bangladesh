"use client";

import { useEffect, useMemo, useState } from "react";
import { Download, RefreshCw, Search, Users } from "lucide-react";
import { fetchSignups, type Signup } from "../../services/api";
import { EmptyState, Notice } from "../ui";

const COLUMNS: { key: keyof Signup; label: string }[] = [
  { key: "full_name", label: "Name" },
  { key: "email", label: "Email" },
  { key: "phone_number", label: "Phone" },
  { key: "company", label: "Company" },
  { key: "designation", label: "Designation" },
  { key: "registered_at", label: "Registered" },
];

const dhaka = (iso: string | null) =>
  iso
    ? new Date(iso).toLocaleString("en-GB", { timeZone: "Asia/Dhaka", day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })
    : "";

function toCsv(rows: Signup[]): string {
  const cell = (v: unknown) => {
    const s = String(v ?? "");
    // Quote every cell; a leading = + - @ is neutralised so spreadsheets never run it as a formula.
    const safe = /^[=+\-@\t\r]/.test(s) ? `'${s}` : s;
    return `"${safe.replace(/"/g, '""')}"`;
  };
  const head = COLUMNS.map((c) => cell(c.label)).join(",");
  const body = rows.map((r) => COLUMNS.map((c) => cell(c.key === "registered_at" ? dhaka(r.registered_at) : r[c.key])).join(","));
  return [head, ...body].join("\r\n");
}

/** Admin console: people who registered with "Register now" (name, email, phone, company, designation). */
export default function AdminSignups() {
  const [rows, setRows] = useState<Signup[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);

  const load = () => {
    setLoading(true);
    setError(null);
    fetchSignups()
      .then(setRows)
      .catch((e) => setError(e?.message || "Could not load sign-ups"))
      .finally(() => setLoading(false));
  };
  useEffect(load, []);

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!rows || !needle) return rows ?? [];
    return rows.filter((r) => COLUMNS.some((c) => String(r[c.key] ?? "").toLowerCase().includes(needle)));
  }, [rows, q]);

  const download = () => {
    const blob = new Blob(["﻿" + toCsv(shown)], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `amarcircular-signups-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  };

  return (
    <section className="panel">
      <div className="flex flex-col gap-3 border-b border-line px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-[17px] font-semibold text-ink">Sign-ups</h2>
          <p className="text-[13.5px] text-ink-3">
            {rows ? `${rows.length} ${rows.length === 1 ? "person has" : "people have"} registered` : "People who used Register now"}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="relative">
            <span className="sr-only">Search sign-ups</span>
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3" strokeWidth={1.75} />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name, bank, email" className="field h-9 w-56 pl-8" />
          </label>
          <button type="button" onClick={load} className="btn-secondary h-9" disabled={loading} aria-label="Refresh">
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} strokeWidth={1.75} />
          </button>
          <button type="button" onClick={download} className="btn-primary h-9" disabled={!shown.length}>
            <Download className="h-4 w-4" strokeWidth={1.75} />
            Download CSV
          </button>
        </div>
      </div>
      <div className="px-5 py-4">
        {error && <Notice kind="error">{error}</Notice>}
        {rows && rows.length === 0 && (
          <EmptyState title="No sign-ups yet" icon={<Users className="h-6 w-6" strokeWidth={1.5} />}>
            When visitors register, their details appear here.
          </EmptyState>
        )}
        {rows && rows.length > 0 && (
          <div className="-mx-5 overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-[14px]">
              <thead className="text-[12.5px] uppercase tracking-wide text-ink-3">
                <tr>
                  {COLUMNS.map((c) => (
                    <th key={c.key} className="whitespace-nowrap px-5 py-2 font-semibold">
                      {c.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {shown.map((r) => (
                  <tr key={r.id} className="border-t border-line align-top">
                    <td className="px-5 py-2.5 font-semibold text-ink">{r.full_name}</td>
                    <td className="px-5 py-2.5">
                      <a href={`mailto:${r.email}`} className="text-accent hover:underline">{r.email}</a>
                    </td>
                    <td className="whitespace-nowrap px-5 py-2.5 tabular-nums">
                      {r.phone_number ? <a href={`tel:${r.phone_number.replace(/[^\d+]/g, "")}`} className="hover:underline">{r.phone_number}</a> : ""}
                    </td>
                    <td className="px-5 py-2.5">{r.company}</td>
                    <td className="px-5 py-2.5 text-ink-2">{r.designation}</td>
                    <td className="whitespace-nowrap px-5 py-2.5 text-ink-3 tabular-nums">{dhaka(r.registered_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {q && shown.length === 0 && <p className="px-5 py-4 text-[14px] text-ink-3">No sign-up matches “{q}”.</p>}
          </div>
        )}
      </div>
    </section>
  );
}
