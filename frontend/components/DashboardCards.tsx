"use client";

import { Fragment } from "react";
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

// Each card has its own light tint, so they are easy to tell apart. The selected card is always solid green,
// which none of the tints is, so the choice stays obvious.
const TINTS: Record<Box, string> = {
  today: "border-bad/15 bg-bad-soft text-ink hover:border-bad/50",
  week: "border-info/15 bg-info-soft text-ink hover:border-info/50",
  month: "border-warn/15 bg-warn-soft text-ink hover:border-warn/50",
  later: "border-line bg-muted-soft text-ink hover:border-ink-3",
};

export const BOX_HINTS: Record<Box, string> = Object.fromEntries(CARDS.map((c) => [c.id, c.hint])) as Record<Box, string>;

/**
 * Today / This week / This month / Read later, on the home page and the dashboard. Each card has its own light tint; the
 * one whose filter is on turns solid green with "Selected". Today gets a red NEW tag when something was issued today.
 */
export default function DashboardCards({
  count,
  active = null,
  signedIn,
  onPick,
  compact = false,
  total,
  allActive = false,
  onAll,
  noLater = false,
}: {
  count: (b: Box) => number | null;
  active?: Box | null;
  signedIn: boolean;
  onPick: (b: Box) => void;
  /** Inside the home page hero: tighter, so four fit beside the picture. */
  compact?: boolean;
  /** "All circulars": the whole library's count (live). Shown as the first card when given. */
  total?: number | null;
  allActive?: boolean;
  onAll?: () => void;
  /** Home page: no Read later card (owner, 2026-11-28). */
  noLater?: boolean;
}) {
  const withAll = total !== undefined;
  // "All circulars" sits 4th, before Read later (owner, 2026-11-26).
  const allCard = withAll ? (
        <button
          type="button"
          onClick={onAll}
          aria-pressed={allActive}
          className={`rounded-[14px] border-2 px-4 py-4 text-left transition-colors sm:col-span-1 ${compact ? "" : "sm:px-5 sm:py-5"} ${
            allActive ? "border-accent bg-accent text-accent-ink shadow-panel" : "border-accent/25 bg-accent-soft text-ink hover:border-accent/50"
          }`}
        >
          <span className="flex items-center justify-between gap-2">
            <span className="text-[15px] font-bold">All circulars</span>
            {allActive && (
              <span className="inline-flex items-center gap-1 rounded-full bg-accent-ink/20 px-2 py-0.5 text-[11px] font-bold tracking-wide">
                <Check className="h-3 w-3" strokeWidth={3} aria-hidden="true" />
                Selected
              </span>
            )}
          </span>
          <span className={`mt-2 block ${compact ? "text-[30px]" : "text-[34px]"} font-bold leading-none tracking-tight tabular-nums`}>
            {total === null ? <SkeletonLine className="mt-1 h-8 w-16" /> : total.toLocaleString("en-US")}
          </span>
          <span className={`mt-2.5 block text-[14px] ${allActive ? "opacity-90" : "text-ink-2"}`}>In the library</span>
        </button>
  ) : null;
  return (
    <div className={`grid grid-cols-2 gap-3 ${withAll && noLater ? "md:grid-cols-4 md:gap-4" : withAll ? (compact ? "sm:grid-cols-5" : "md:grid-cols-5 md:gap-4") : compact ? "sm:grid-cols-4" : "md:grid-cols-4 md:gap-4"}`}>
      {CARDS.map(({ id, label, hint }) => {
        const n = count(id);
        const locked = id === "later" && !signedIn;
        const fresh = id === "today" && !!n && n > 0;
        const on = active === id;
        // Light tint per card; the selected one is solid green with a tick.
        const look = on
          ? "border-accent bg-accent text-accent-ink shadow-panel"
          : TINTS[id];
        const numberColour = on ? "" : fresh ? "text-bad" : "text-ink";
        const hintColour = on ? "opacity-90" : "text-ink-2";
        return (
          <Fragment key={id}>
          {id === "later" && allCard}
          {!(noLater && id === "later") && (
          <button
            type="button"
            onClick={() => onPick(id)}
            aria-pressed={active === id}
            className={`rounded-[14px] border-2 px-4 py-4 text-left transition-colors ${compact ? "" : "sm:px-5 sm:py-5"} ${withAll && id === "later" ? "col-span-2 sm:col-span-1" : ""} ${look}`}
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
          )}
          </Fragment>
        );
      })}
    </div>
  );
}
