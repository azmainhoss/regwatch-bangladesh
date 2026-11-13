"use client";

import Link from "next/link";
import { GitCompareArrows } from "lucide-react";
import type { DocumentItem, RelLink } from "@/services/api";

/** The compare screen's address for two stored files, older on the left. */
export function compareHref(leftVersionId: string, rightVersionId: string, docId?: string) {
  const params = new URLSearchParams({ left: leftVersionId, right: rightVersionId });
  if (docId) params.set("doc", docId);
  return `/compare?${params.toString()}`;
}

const OLDER_VERBS: Record<string, string> = { REPLACES: "replaces", SUPERSEDES: "supersedes", AMENDS: "amends", REPEALS: "repeals" };

/**
 * Buttons that open the compare screen for this circular: against the circular it replaces or amends
 * (when a stored circular is linked), and between its own stored files when it has more than one.
 */
export default function CompareButtons({ doc, outgoing }: { doc: DocumentItem; outgoing: RelLink[] }) {
  const currentVersion = doc.current_version_id || doc.versions?.[0]?.id;
  if (!currentVersion) return null;

  // Prefer the circular this one replaces; then one it amends or repeals. Rejected links never reach here.
  const order = ["REPLACES", "SUPERSEDES", "AMENDS", "REPEALS"];
  const usable = outgoing
    .filter((l) => l.target?.current_version_id && OLDER_VERBS[l.relationship_type] && l.target.id !== doc.id)
    .sort((a, b) => order.indexOf(a.relationship_type) - order.indexOf(b.relationship_type));
  const seen = new Set<string>();
  const targets = usable.filter((l) => (seen.has(l.target!.id) ? false : (seen.add(l.target!.id), true))).slice(0, 3);

  const versions = [...(doc.versions ?? [])].sort((a, b) => a.version_number - b.version_number);
  const olderVersion = versions.length >= 2 ? versions[versions.length - 2] : null;
  const newestVersion = versions.length >= 2 ? versions[versions.length - 1] : null;

  if (targets.length === 0 && !olderVersion) return null;
  return (
    <>
      {targets.map((l) => (
        <Link
          key={l.id}
          href={compareHref(l.target!.current_version_id as string, currentVersion, doc.id)}
          className="btn-secondary max-w-full !whitespace-normal text-left"
          data-testid="compare-with-target"
        >
          <GitCompareArrows className="h-4 w-4" strokeWidth={1.75} />
          {`Compare with the circular it ${OLDER_VERBS[l.relationship_type]}`}
          <span className="font-normal text-ink-3">{l.target!.reference_number}</span>
          {l.verification_status === "PENDING_REVIEW" && <span className="text-2xs font-normal text-ink-3">(unconfirmed)</span>}
        </Link>
      ))}
      {olderVersion && newestVersion && (
        <Link href={compareHref(olderVersion.id, newestVersion.id, doc.id)} className="btn-secondary max-w-full" data-testid="compare-versions">
          <GitCompareArrows className="h-4 w-4" strokeWidth={1.75} />
          Compare versions
        </Link>
      )}
    </>
  );
}
