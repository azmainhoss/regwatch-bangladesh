"use client";

import { SkeletonLine } from "@/components/ui";
import type { Period } from "@/services/libraryApi";

export type Box = Period | "later";

const CARDS: { id: Box; label: string; hint: string }[] = [
  { id: "today", label: "Today", hint: "Issued today" },
  { id: "week", label: "This week", hint: "Since Sunday" },
  { id: "month", label: "This month", hint: "Since the 1st" },
  { id: "later", label: "Read later", hint: "Saved by you" },
];

export const BOX_HINTS: Record<Box, string> = Object.fromEntries(CARDS.map((c) => [c.id, c.hint])) as Record<Box, string>;

/**
 * Today / This week / This month / Read later, on the home page and the dashboard. Each card keeps its own colour;
 * Today turns red with a NEW tag only when something was issued today. The card whose filter is on gets a ring.
 */
export default function DashboardCards({
  count,
  active = null,
  signedIn,
  onPick,
}: {
  count: (b: Box) => number | null;
  active?: Box | null;
  signedIn: boolean;
  onPick: (b: Box) => void;
}) {
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4 md:gap-4">
      {CARDS.map(({ id, label, hint }) => {
        const n = count(id);
        const locked = id === "later" && !signedIn;
        const fresh = id === "today" && !!n && n > 0;
        const look =
          id === "week"
            ? "border-accent bg-accent text-accent-ink hover:bg-accent-hover"
            : id === "month"
              ? "border-accent-soft bg-accent-soft text-accent hover:border-accent/40"
              : fresh
                ? "border-bad bg-surface text-ink ring-1 ring-inset ring-bad hover:bg-bad-soft/40"
                : "border-line bg-surface text-ink hover:border-accent/50";
        const numberColour = id === "week" ? "" : id === "month" ? "text-ink" : fresh ? "text-bad" : "text-ink";
        const hintColour = id === "week" ? "opacity-90" : id === "month" ? "" : "text-ink-3";
        return (
          <button
            key={id}
            type="button"
            onClick={() => onPick(id)}
            aria-pressed={active === id}
            className={`rounded-[14px] border px-4 py-4 text-left transition-colors sm:px-5 sm:py-5 ${look} ${
              active === id ? "ring-2 ring-ink ring-offset-2 ring-offset-canvas" : ""
            }`}
          >
            <span className="flex items-center justify-between gap-2">
              <span className="text-[15px] font-bold">{label}</span>
              {fresh && (
                <span className="inline-flex items-center gap-1 rounded-full bg-bad px-2 py-0.5 text-[11px] font-bold tracking-wide text-surface">
                  <span className="h-1.5 w-1.5 rounded-full bg-surface" aria-hidden="true" />
                  NEW
                </span>
              )}
            </span>
            <span className={`mt-2 block text-[34px] font-bold leading-none tracking-tight tabular-nums ${numberColour}`}>
              {locked ? "-" : n === null ? <SkeletonLine className="mt-1 h-8 w-12" /> : n}
            </span>
            <span className={`mt-2.5 block text-[14px] ${hintColour}`}>{locked ? "Register to save" : hint}</span>
          </button>
        );
      })}
    </div>
  );
}
