"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/services/api";
import { Notice } from "./ui";

interface Req {
  id: string;
  plan: string;
  seats: number;
  status: string;
  organization_name?: string | null;
  contact_phone?: string | null;
  note?: string | null;
  requested_by?: string | null;
  created_at: string;
}

/** Plan requests: switch a plan on once payment is received, or end it. Changes show at once. */
export default function AdminPlans() {
  const [rows, setRows] = useState<Req[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    apiFetch("/plans/requests", { cache: "no-store" })
      .then(async (r) => (r.ok ? setRows(await r.json()) : setError("Could not load plan requests.")))
      .catch(() => setError("Could not load plan requests."));

  useEffect(() => {
    load();
  }, []);

  const decide = async (id: string, decision: "activate" | "end") => {
    const before = rows;
    setRows((rs) => rs?.map((r) => (r.id === id ? { ...r, status: decision === "activate" ? "ACTIVE" : "ENDED" } : r)) ?? null);
    const r = await apiFetch(`/plans/requests/${id}/${decision}`, { method: "POST" }).catch(() => null);
    if (!r || !r.ok) {
      setRows(before);
      setError("That change was not saved. Try again.");
    }
  };

  return (
    <section className="panel space-y-3">
      <h2 className="text-[17px] font-semibold text-ink">Plans</h2>
      <p className="text-[13.5px] text-ink-3">Switch a plan on once the payment is in. Enterprise covers everyone in that bank&apos;s workspace.</p>
      {error && <Notice kind="error">{error}</Notice>}
      {rows === null ? (
        <p className="text-[14px] text-ink-3">Loading...</p>
      ) : rows.length === 0 ? (
        <p className="text-[14px] text-ink-3">No plan requests yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[13.5px]">
            <thead className="text-ink-3">
              <tr>
                <th className="py-1.5 pr-3">Plan</th>
                <th className="py-1.5 pr-3">Who</th>
                <th className="py-1.5 pr-3">Seats</th>
                <th className="py-1.5 pr-3">Phone</th>
                <th className="py-1.5 pr-3">Status</th>
                <th className="py-1.5" />
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {rows.map((r) => (
                <tr key={r.id}>
                  <td className="py-2 pr-3 font-semibold text-ink">{r.plan.charAt(0) + r.plan.slice(1).toLowerCase()}</td>
                  <td className="py-2 pr-3 text-ink-2">
                    {r.organization_name || r.requested_by || "-"}
                    {r.note && <span className="block text-[12.5px] text-ink-3">{r.note}</span>}
                  </td>
                  <td className="py-2 pr-3 tabular-nums">{r.seats}</td>
                  <td className="py-2 pr-3">{r.contact_phone || "-"}</td>
                  <td className="py-2 pr-3">{r.status === "REQUESTED" ? "Waiting for payment" : r.status === "ACTIVE" ? "On" : "Ended"}</td>
                  <td className="py-2 text-right">
                    {r.status !== "ACTIVE" ? (
                      <button type="button" className="btn-secondary py-1" onClick={() => decide(r.id, "activate")}>
                        Switch on
                      </button>
                    ) : (
                      <button type="button" className="btn-ghost py-1" onClick={() => decide(r.id, "end")}>
                        End
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
