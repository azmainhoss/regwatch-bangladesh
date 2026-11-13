"use client";

import { useState } from "react";
import { Link2, RefreshCw } from "lucide-react";
import { relinkRelationships } from "@/services/api";
import { clearNotice, loadPending, refreshAll, useRelState } from "@/services/relationshipsStore";
import { LinkCard } from "./LinksView";
import { EmptyState, Notice, SkeletonLine } from "./ui";

/**
 * Links the reader found between circulars that nobody has confirmed yet. Approving one makes it
 * count toward the in-force status; rejecting it removes it. Both show on every screen at once.
 */
export default function AdminLinksPanel() {
  const rel = useRelState();
  const [relinking, setRelinking] = useState(false);
  const [relinkNote, setRelinkNote] = useState<string | null>(null);
  const [relinkError, setRelinkError] = useState<string | null>(null);

  const relink = async () => {
    try {
      setRelinking(true);
      setRelinkError(null);
      setRelinkNote(null);
      const res = await relinkRelationships();
      setRelinkNote(`${res.message} ${res.still_unlinked} cited circular(s) are still not in the library.`);
      await loadPending();
      void refreshAll();
    } catch (e: any) {
      setRelinkError(e.message || "Could not look for link targets.");
    } finally {
      setRelinking(false);
    }
  };

  const links = rel.pending?.links ?? [];

  return (
    <section className="panel" data-testid="admin-links">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-5 py-4">
        <div>
          <h2 className="text-[17px] font-semibold text-ink">Links awaiting review</h2>
          <p className="mt-0.5 max-w-prose text-[13.5px] text-ink-3">
            Read the quote and check it says what the link claims. Only approved links change whether a circular is in force.
          </p>
        </div>
        <button type="button" onClick={relink} disabled={relinking} className="btn-secondary">
          <RefreshCw className={`h-4 w-4 ${relinking ? "animate-spin" : ""}`} strokeWidth={1.75} />
          {relinking ? "Looking..." : "Look for link targets again"}
        </button>
      </div>
      <div className="space-y-3 p-5">
        {rel.notice && (
          <Notice kind={rel.notice.kind} onDismiss={clearNotice}>
            {rel.notice.text}
          </Notice>
        )}
        {relinkNote && <Notice kind="success" onDismiss={() => setRelinkNote(null)}>{relinkNote}</Notice>}
        {relinkError && <Notice kind="error" onDismiss={() => setRelinkError(null)}>{relinkError}</Notice>}
        {rel.pendingError && (
          <Notice kind="error">
            {rel.pendingError}{" "}
            <button type="button" className="font-semibold underline" onClick={() => void loadPending()}>
              Try again
            </button>
          </Notice>
        )}
        {!rel.pending && !rel.pendingError ? (
          <div className="space-y-3" aria-busy="true">
            <SkeletonLine className="h-24 w-full" />
            <SkeletonLine className="h-24 w-full" />
          </div>
        ) : links.length === 0 && !rel.pendingError ? (
          <EmptyState title="Nothing to review" icon={<Link2 className="h-6 w-6" strokeWidth={1.5} />}>
            Every link found so far has been confirmed or rejected.
          </EmptyState>
        ) : (
          <ul className="space-y-3">
            {links.map((l) => (
              <li key={l.id}>
                <LinkCard link={l} isAdmin />
              </li>
            ))}
          </ul>
        )}
        {rel.pending && rel.pending.total > links.length && (
          <p className="text-[13px] text-ink-3">Showing {links.length} of {rel.pending.total}. Review these to see the rest.</p>
        )}
      </div>
    </section>
  );
}
