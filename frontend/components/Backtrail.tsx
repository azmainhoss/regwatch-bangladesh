"use client";

import Link from "next/link";
import { CornerDownRight, CornerUpLeft, GitBranch } from "lucide-react";
import type { RelLink, RelStatus } from "@/services/api";

const VERB_IN: Record<string, string> = {
  AMENDS: "Amended by",
  SUPERSEDES: "Replaced by",
  REPLACES: "Replaced by",
  REPEALS: "Repealed by",
  CLARIFIES: "Clarified by",
};

/**
 * The trail of a circular in one glance: which newer circulars changed it, which newer circulars cite it
 * ("Cited by"), and which older circulars it cites ("Cites"). The full chain is on the History and links page.
 */
export interface BackLink {
  id: string;
  docId: string | null;
  label: string;
  quote?: string;
}

export default function Backtrail({ documentId, status, back }: { documentId: string; status?: RelStatus; back: BackLink[] }) {
  const incoming = status?.verified_incoming ?? [];
  const changedBy = incoming.filter((l) => VERB_IN[l.relationship_type]);
  // Newer circulars that mention this one without changing it (references, implements, ...).
  // Each citing circular once.
  const citedBy = incoming
    .filter((l) => !VERB_IN[l.relationship_type] && l.source)
    .filter((l, i, all) => all.findIndex((o) => (o.source.id ?? o.source.title) === (l.source.id ?? l.source.title)) === i);
  const current = status?.current_version && status.current_version.id !== documentId ? status.current_version : null;
  if (changedBy.length === 0 && citedBy.length === 0 && back.length === 0 && !current) return null;

  const chip = (href: string | null, label: string, title?: string) =>
    href ? (
      <Link key={href + label} href={href} title={title} className="rounded-full bg-sunken px-2.5 py-0.5 font-semibold text-ink hover:bg-accent-soft hover:text-accent">
        {label}
      </Link>
    ) : (
      <span key={label} title={title} className="rounded-full bg-sunken px-2.5 py-0.5 text-ink-2">
        {label}
      </span>
    );

  const linkTo = (l: RelLink, side: "source" | "target") => {
    const ref = side === "source" ? l.source : l.target;
    return ref?.id ? `/dashboard?doc=${ref.id}` : null;
  };

  return (
    <div className="space-y-1.5 rounded-panel border border-line bg-sunken/40 px-3 py-2.5 text-[13px]" data-testid="backtrail">
      {current && (
        <p className="flex flex-wrap items-center gap-1.5 text-ink-2">
          <CornerDownRight className="h-3.5 w-3.5 text-warn" />
          <span className="font-semibold text-warn">The rule now in force is in</span>
          {chip(`/dashboard?doc=${current.id}`, current.reference_number || current.title)}
        </p>
      )}
      {changedBy.length > 0 && (
        <p className="flex flex-wrap items-center gap-1.5 text-ink-2">
          <CornerDownRight className="h-3.5 w-3.5 text-ink-3" />
          {changedBy.map((l) => (
            <span key={l.id} className="inline-flex items-center gap-1.5">
              <span>{VERB_IN[l.relationship_type]}</span>
              {chip(linkTo(l, "source"), l.source.reference_number || l.source.title)}
            </span>
          ))}
        </p>
      )}
      {citedBy.length > 0 && (
        <p className="flex flex-wrap items-center gap-1.5 text-ink-2" data-testid="cited-by">
          <CornerDownRight className="h-3.5 w-3.5 text-ink-3" />
          <span>Cited by:</span>
          {citedBy.slice(0, 8).map((l) => chip(linkTo(l, "source"), l.source.reference_number || l.source.title))}
          {citedBy.length > 8 && <span className="text-ink-3">+{citedBy.length - 8} more</span>}
        </p>
      )}
      {back.length > 0 && (
        <p className="flex flex-wrap items-center gap-1.5 text-ink-2">
          <CornerUpLeft className="h-3.5 w-3.5 text-ink-3" />
          <span>Cites:</span>
          {back.slice(0, 8).map((l) => chip(l.docId ? `/dashboard?doc=${l.docId}` : null, l.label, l.quote))}
          {back.length > 8 && <span className="text-ink-3">+{back.length - 8} more</span>}
        </p>
      )}
      <Link href={`/circular/${documentId}/links`} className="inline-flex items-center gap-1 font-semibold text-accent hover:underline">
        <GitBranch className="h-3.5 w-3.5" /> Full history and links
      </Link>
    </div>
  );
}
