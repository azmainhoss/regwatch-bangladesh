"use client";

import { useState } from "react";
import Link from "next/link";
import { CheckCircle2, Circle, UserCheck } from "lucide-react";
import { markAssignment, useAssignments } from "@/services/assignmentsStore";

const fmt = (v?: string | null) => {
  if (!v) return "";
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? v : d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
};

/** Circulars handed to me by a colleague, and the ones I handed out. Hidden when there are none. */
export default function AssignedPanel({ userId }: { userId: string }) {
  const { items, loaded } = useAssignments();
  const [picked, setTab] = useState<"mine" | "by_me" | null>(null);
  const [showDone, setShowDone] = useState(false);
  if (!loaded || items.length === 0) return null;

  const mine = items.filter((a) => a.assignee_user_id === userId);
  const byMe = items.filter((a) => a.assigned_by_user_id === userId && a.assignee_user_id !== userId);
  // Until the person picks a tab: "To you" when something is assigned to them, else "By you".
  const tab = picked ?? (mine.some((a) => a.status === "OPEN") || byMe.length === 0 ? "mine" : "by_me");
  const list = (tab === "mine" ? mine : byMe).filter((a) => showDone || a.status === "OPEN");
  const openMine = mine.filter((a) => a.status === "OPEN").length;
  const today = new Date().toISOString().slice(0, 10);

  return (
    <section aria-label="Assigned circulars" className="rounded-panel border border-line bg-surface">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-3.5 py-2.5">
        <h2 className="flex items-center gap-2 text-[14.5px] font-semibold text-ink">
          <UserCheck className="h-4 w-4 text-accent" strokeWidth={1.9} />
          Assigned
          {openMine > 0 && <span className="rounded-full bg-accent px-2 py-px text-[12px] font-semibold text-accent-ink tabular-nums">{openMine} for you</span>}
        </h2>
        <div className="flex items-center gap-2">
          <div role="tablist" className="inline-flex rounded-control bg-sunken p-0.5 text-[12.5px]">
            {(
              [
                { id: "mine", label: `To you (${mine.length})` },
                { id: "by_me", label: `By you (${byMe.length})` },
              ] as const
            ).map((t) => (
              <button
                key={t.id}
                type="button"
                role="tab"
                aria-selected={tab === t.id}
                onClick={() => setTab(t.id)}
                className={`rounded-[7px] px-2.5 py-1 font-semibold ${tab === t.id ? "bg-surface text-ink shadow-sm" : "text-ink-3 hover:text-ink"}`}
              >
                {t.label}
              </button>
            ))}
          </div>
          <label className="flex items-center gap-1 text-[12.5px] text-ink-3">
            <input type="checkbox" checked={showDone} onChange={(e) => setShowDone(e.target.checked)} /> Done too
          </label>
        </div>
      </header>
      {list.length === 0 ? (
        <p className="px-3.5 py-3 text-[13.5px] text-ink-3">{tab === "mine" ? "Nothing open for you. Nice." : "Nothing open that you assigned."}</p>
      ) : (
        <ul className="max-h-64 divide-y divide-line overflow-y-auto">
          {list.map((a) => {
            const late = a.status === "OPEN" && a.due_date && a.due_date < today;
            return (
              <li key={a.id} className="flex items-start gap-2.5 px-3.5 py-2.5">
                <button
                  type="button"
                  onClick={() => markAssignment(a.id, a.status === "OPEN" ? "DONE" : "OPEN")}
                  aria-label={a.status === "OPEN" ? "Mark done" : "Open again"}
                  title={a.status === "OPEN" ? "Mark done" : "Open again"}
                  className={`mt-0.5 shrink-0 ${a.status === "DONE" ? "text-accent" : "text-ink-3 hover:text-accent"}`}
                >
                  {a.status === "DONE" ? <CheckCircle2 className="h-5 w-5" /> : <Circle className="h-5 w-5" />}
                </button>
                <Link href={`/?doc=${a.document_id}`} className="min-w-0 flex-1 hover:underline">
                  <span className="flex flex-wrap items-baseline gap-x-2">
                    <span className={`refno ${a.status === "DONE" ? "line-through opacity-60" : ""}`}>{a.reference_number || "Circular"}</span>
                    <span className="text-[12.5px] text-ink-3">
                      {tab === "mine" ? `from ${a.assigned_by_name}` : `to ${a.assignee_name}`}
                      {a.due_date && <span className={late ? " font-semibold text-danger" : ""}> · by {fmt(a.due_date)}</span>}
                    </span>
                  </span>
                  <span className="block truncate text-[13.5px] text-ink-2">{a.note || a.title}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
