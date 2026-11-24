"use client";

import { Check } from "lucide-react";
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
 * Today / This week / This month / Read later, on the home page and the dashboard. All cards are white; the one whose
 * filter is on turns solid green with "Selected". Today gets a red NEW tag when something was issued today.
 */
export default function DashboardCards({
  count,
  active = null,
  signedIn,
  onPick,
  compact = false,
}: {
  count: (b: Box) => number | null;
  active?: Box | null;
  signedIn: boolean;
  onPick: (b: Box) => void;
  /** Inside the home page hero: tighter, so four fit beside the picture. */
  compact?: boolean;
}) {
  return (
    <div className={`grid grid-cols-2 gap-3 ${compact ? "sm:grid-cols-4" : "md:grid-cols-4 md:gap-4"}`}>
      {CARDS.map(({ id, label, hint }) => {
        const n = count(id);
        const locked = id === "later" && !signedIn;
        const fresh = id === "today" && !!n && n > 0;
        const on = active === id;
        // One rule: every card is white; the selected one is solid green with a tick. Today's NEW tag is the only red.
        const look = on
          ? "border-accent bg-accent text-accent-ink shadow-panel"
          : "border-line bg-surface text-ink hover:border-accent hover:bg-accent-soft/40";
        const numberColour = on ? "" : fresh ? "text-bad" : "text-ink";
        const hintColour = on ? "opacity-90" : "text-ink-3";
        return (
          <button
            key={id}
            type="button"
            onClick={() => onPick(id)}
            aria-pressed={active === id}
            className={`rounded-[14px] border-2 px-4 py-4 text-left transition-colors ${compact ? "" : "sm:px-5 sm:py-5"} ${look}`}
          >
            <span className="flex items-center justify-between gap-2">
              <span className="text-[15px] font-bold">{label}</span>
              {on ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-accent-ink/20 px-2 py-0.5 text-[11px] font-bold tracking-wide">
                  <Check className="h-3 w-3" strokeWidth={3} aria-hidden="true" />
                  Selected
                </span>
              ) : fresh && (
                <span className="inline-flex items-center gap-1 rounded-full bg-bad px-2 py-0.5 text-[11px] font-bold tracking-wide text-surface">
                  <span className="h-1.5 w-1.5 rounded-full bg-surface" aria-hidden="true" />
                  NEW
                </span>
              )}
            </span>
            <span className={`mt-2 block ${compact ? "text-[30px]" : "text-[34px]"} font-bold leading-none tracking-tight tabular-nums ${numberColour}`}>
              {locked ? "-" : n === null ? <SkeletonLine className="mt-1 h-8 w-12" /> : n}
            </span>
            <span className={`mt-2.5 block text-[14px] ${hintColour}`}>{locked ? "Register to save" : hint}</span>
          </button>
        );
      })}
    </div>
  );
}
