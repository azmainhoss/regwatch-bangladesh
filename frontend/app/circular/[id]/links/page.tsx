"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, GitBranch } from "lucide-react";
import {
  AUTH_CHANGED_EVENT,
  AuthUser,
  DocumentItem,
  fetchCurrentUser,
  fetchDocument,
  getStoredUser,
} from "@/services/api";
import { clearNotice, inForceOf, loadGraph, loadStatus, loadTimeline, seedDocuments, useRelState } from "@/services/relationshipsStore";
import CompareButtons from "@/components/CompareButtons";
import { GraphLegend, LinkCard, LinksGraph, LinksTimeline, edgeToLink } from "@/components/LinksView";
import { AwaitingReviewTag, InForceBadge } from "@/components/StatusBadge";
import { EmptyState, Notice, SkeletonLine, titleWithoutRef } from "@/components/ui";

const VERDICT: Record<string, string> = {
  IN_FORCE: "No confirmed circular has changed or replaced this one, so it is in force.",
  AMENDED: "This circular is still in force, but a later circular has changed it.",
  REPLACED: "A later circular replaces this one.",
  REPEALED: "A later circular repeals this one.",
};

export default function CircularLinksPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id;

  const [doc, setDoc] = useState<DocumentItem | null>(null);
  const [docError, setDocError] = useState<string | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [depth, setDepth] = useState(2);
  const [selectedEdge, setSelectedEdge] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const rel = useRelState();

  useEffect(() => {
    setUser(getStoredUser());
    fetchCurrentUser()
      .then((u) => setUser(u))
      .catch(() => setUser(getStoredUser()));
    const onChanged = () => setUser(getStoredUser());
    window.addEventListener(AUTH_CHANGED_EVENT, onChanged);
    return () => window.removeEventListener(AUTH_CHANGED_EVENT, onChanged);
  }, []);

  useEffect(() => {
    if (!id) return;
    let alive = true;
    setDocError(null);
    fetchDocument(id)
      .then((d) => {
        if (!alive) return;
        setDoc(d);
        seedDocuments([d]);
      })
      .catch((e: any) => alive && setDocError(e.message || "Could not open that circular."));
    return () => {
      alive = false;
    };
  }, [id, user?.id]);

  // Shows what is already known at once, and fetches fresh copies in the background.
  useEffect(() => {
    if (!id) return;
    setLoadError(null);
    Promise.all([loadStatus(id), loadTimeline(id)]).catch((e: any) => setLoadError(e.message || "Could not load the history."));
  }, [id, user?.id]);

  useEffect(() => {
    if (!id) return;
    loadGraph(id, depth).catch((e: any) => setLoadError(e.message || "Could not load the graph."));
  }, [id, depth, user?.id]);

  const status = id ? rel.status[id] : undefined;
  const timeline = id ? rel.timeline[id] : undefined;
  const graph = id ? rel.graph[`${id}:${depth}`] : undefined;
  const info = doc ? inForceOf(rel, doc) : status ? { status: status.in_force_status, byId: status.in_force_by?.id, byRef: status.in_force_by?.reference_number } : undefined;
  const isAdmin = !!user?.is_superuser;

  const selectedLink = useMemo(() => {
    if (!graph || !selectedEdge) return null;
    const edge = graph.edges.find((e) => e.id === selectedEdge);
    return edge ? edgeToLink(edge, graph.nodes) : null;
  }, [graph, selectedEdge]);

  if (docError) {
    return (
      <div className="space-y-4">
        <Link href="/" className="btn-ghost -ml-2">
          <ArrowLeft className="h-4 w-4" /> Circulars
        </Link>
        <Notice kind="error">{docError}</Notice>
      </div>
    );
  }

  const unconfirmed = status?.unconfirmed_incoming ?? [];
  const pendingOutgoing = (status?.outgoing ?? []).filter((l) => l.verification_status === "PENDING_REVIEW");
  const waiting = [...unconfirmed, ...pendingOutgoing];

  return (
    <div className="space-y-6">
      <div>
        <Link href={id ? `/?doc=${id}` : "/"} className="btn-ghost -ml-2" data-testid="back-to-circular">
          <ArrowLeft className="h-4 w-4" strokeWidth={1.75} />
          Back to the circular
        </Link>
      </div>

      <header className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="refno">{doc?.reference_number || status?.current_version?.reference_number || "Circular"}</span>
          <InForceBadge info={info} />
          {waiting.length > 0 && <AwaitingReviewTag count={waiting.length} />}
        </div>
        {doc ? (
          <h1 className="max-w-[60ch] text-[24px] font-semibold leading-[1.3] tracking-[-0.01em] text-ink [text-wrap:balance]">
            {titleWithoutRef(doc.title, doc.reference_number)}
          </h1>
        ) : (
          <SkeletonLine className="h-7 w-2/3" />
        )}
        <p className="flex items-center gap-2 text-[14.5px] text-ink-2">
          <GitBranch className="h-4 w-4 text-ink-3" strokeWidth={1.75} aria-hidden />
          History and links
        </p>
        {rel.notice && (
          <Notice kind={rel.notice.kind} onDismiss={clearNotice}>
            {rel.notice.text}
          </Notice>
        )}
        {loadError && <Notice kind="error">{loadError}</Notice>}
      </header>

      {/* The verdict */}
      <section className="rounded-panel border border-line bg-surface p-5 shadow-panel" aria-labelledby="verdict-title" data-testid="verdict">
        <h2 id="verdict-title" className="section-title">
          Is it still in force?
        </h2>
        {!info ? (
          <SkeletonLine className="mt-3 h-4 w-80 max-w-full" />
        ) : (
          <div className="mt-2 space-y-2">
            <p className="max-w-prose text-[15.5px] text-ink">{VERDICT[info.status] ?? ""}</p>
            {info.byRef && info.status !== "IN_FORCE" && (
              <p className="text-[14.5px] text-ink-2">
                Changed by{" "}
                {info.byId ? (
                  <Link href={`/?doc=${info.byId}`} className="refno hover:underline">
                    {info.byRef}
                  </Link>
                ) : (
                  <span className="refno">{info.byRef}</span>
                )}
              </p>
            )}
            {status?.current_version && status.current_version.id !== id && (
              <p className="text-[14.5px] text-ink-2">
                The current version is{" "}
                <Link href={`/?doc=${status.current_version.id}`} className="refno hover:underline" data-testid="current-version-link">
                  {status.current_version.reference_number || status.current_version.title}
                </Link>
                .
              </p>
            )}
            {status?.chain_has_cycle && (
              <Notice kind="warning">The links form a loop (each circular says it replaces the other), so no single current version can be named. Please review them.</Notice>
            )}
            <p className="max-w-prose text-[13px] text-ink-3">
              Only links that have been confirmed count. Links still awaiting review are shown below in a lighter style and change nothing.
            </p>
          </div>
        )}
        {doc && (
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <CompareButtons doc={doc} outgoing={status?.outgoing ?? []} />
          </div>
        )}
      </section>

      {/* Timeline */}
      <section className="space-y-3" aria-labelledby="timeline-title">
        <h2 id="timeline-title" className="section-title">
          History
          <span className="ml-2 text-[13px] font-normal text-ink-3">Oldest first. Each change shows the exact words and the page they are on.</span>
        </h2>
        {!timeline ? (
          <div className="space-y-3" aria-busy="true">
            <SkeletonLine className="h-4 w-48" />
            <SkeletonLine className="h-16 w-full" />
          </div>
        ) : timeline.items.length <= 1 && timeline.items.every((i) => i.changes.length === 0) ? (
          <EmptyState title="No changes recorded">No other circular is linked to this one as amending, replacing or repealing it, or being changed by it.</EmptyState>
        ) : (
          <LinksTimeline timeline={timeline} isAdmin={isAdmin} />
        )}
      </section>

      {/* Graph */}
      <section className="space-y-3" aria-labelledby="graph-title">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h2 id="graph-title" className="section-title">
            Links graph
          </h2>
          <div className="hidden items-center gap-2 text-[13px] text-ink-2 sm:flex">
            <label htmlFor="graph-depth">How far to follow links</label>
            <select id="graph-depth" value={depth} onChange={(e) => setDepth(Number(e.target.value))} className="field h-8 w-auto py-0">
              <option value={1}>1 step</option>
              <option value={2}>2 steps</option>
              <option value={3}>3 steps</option>
            </select>
          </div>
        </div>
        {/* Phone: the graph would be too small to read, so the history above is the view. */}
        <p className="rounded-panel border border-dashed border-line-strong px-4 py-3 text-[13.5px] text-ink-3 sm:hidden" data-testid="graph-phone-note">
          The graph needs a wider screen. The history above lists the same links with their quotes.
        </p>
        <div className="hidden space-y-3 sm:block">
          {!graph ? (
            <SkeletonLine className="h-40 w-full" />
          ) : graph.edges.length === 0 ? (
            <EmptyState title="Nothing to draw">This circular has no links to other circulars yet.</EmptyState>
          ) : (
            <>
              <LinksGraph graph={graph} selectedEdgeId={selectedEdge} onSelectEdge={setSelectedEdge} />
              <GraphLegend />
              {graph.truncated && <p className="text-[13px] text-ink-3">The graph is large, so only part of it is drawn.</p>}
              {selectedLink ? (
                <div className="space-y-1.5" data-testid="selected-link">
                  <p className="text-[13px] font-semibold text-ink-2">Selected link</p>
                  <LinkCard link={selectedLink} isAdmin={isAdmin} />
                </div>
              ) : (
                <p className="text-[13px] text-ink-3">Select an arrow to read the exact quote behind it.</p>
              )}
            </>
          )}
        </div>
      </section>

      {/* Not confirmed */}
      {waiting.length > 0 && (
        <section className="space-y-3" aria-labelledby="waiting-title" data-testid="awaiting-section">
          <h2 id="waiting-title" className="section-title">
            Awaiting review
            <span className="ml-2 text-[13px] font-normal text-ink-3">These links have not been confirmed, so they do not change the status above.</span>
          </h2>
          <div className="space-y-2">
            {waiting.map((l) => (
              <LinkCard key={l.id} link={l} isAdmin={isAdmin} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
