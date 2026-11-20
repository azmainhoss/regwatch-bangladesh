"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowUpRight, BookOpenText, CheckCircle2, EyeOff, FileDown, GitBranch, ListPlus, Lock, RefreshCw, Send, ShieldCheck, Sparkles } from "lucide-react";
import {
  AuthUser,
  ClaimItem,
  ClaimSection,
  DocumentItem,
  DocumentPage,
  QuoteBox,
  type ResearchCitation,
  documentPdfUrl,
  fetchAnalysisStatus,
  fetchReadingStatus,
  type ReadingStatus,
  openDocumentPdf,
  reextractDocument,
  triggerDocumentAnalysis,
} from "@/services/api";
import StatusBadge, { AwaitingReviewTag, InForceBadge, PrivateTag, Tag } from "./StatusBadge";
import CompareButtons from "./CompareButtons";
import { loadStatus, inForceOf, useRelState } from "@/services/relationshipsStore";
import { askReview, askReviewAll, clearClaimsNotice, reloadDoc, useDocClaims } from "@/services/claimsStore";
import { SECTION_ORDER, adminStateText, checkedBadge, checkedTag, entityLabel, minutesText, placeholderLines, readable, type PlaceholderLine } from "@/services/claimWords";
import { relLabel } from "./LinksView";
import PagePanel, { type PageHighlight } from "./PagePanel";
import AddToRegisterModal from "./workspace/AddToRegisterModal";
import { rememberOrg, useAddRights } from "./workspace/useAddRights";
import { ensureWorkspace, orgItems, useWorkspace } from "@/services/workspaceStore";
import { EASE_OUT, Notice, SkeletonLine, hasBangla, titleWithoutRef } from "./ui";

export interface QaResponse {
  answer: string;
  is_grounded?: boolean;
  citations?: Array<{ page_number?: number; page?: number; verbatim_excerpt?: string; quoted_text?: string; quote?: string }>;
}

interface Props {
  doc: DocumentItem;
  pages: DocumentPage[];
  pageNumber: number;
  setPageNumber: (n: number) => void;
  pagePanelOpen: boolean;
  setPagePanelOpen: (open: boolean) => void;
  highlight: PageHighlight | null;
  setHighlight: (h: PageHighlight | null) => void;
  qaQuery: string;
  setQaQuery: (q: string) => void;
  qaLoading: boolean;
  qaResponse: QaResponse | null;
  qaMatches?: ResearchCitation[] | null;
  qaError: string | null;
  onAsk: (e: React.FormEvent) => void;
  currentUser: AuthUser | null;
  onSignIn: () => void;
  onRefresh: () => void;
  onPageSaved: (page: DocumentPage) => void;
  /** Set when the pages shown are those of an older version (opened from a register item). */
  viewingVersionId?: string | null;
}

function formatDate(value?: string | null) {
  if (!value) return null;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

function Section({ title, count, children, aside }: { title: string; count?: number; children: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <section className="border-t border-line pt-5">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h3 className="section-title">
          {title}
          {typeof count === "number" && <span className="ml-1.5 font-normal text-ink-3 tabular-nums">{count}</span>}
        </h3>
        {aside}
      </div>
      {children}
    </section>
  );
}

function PageLink({ page, onClick }: { page?: number | null; onClick: () => void }) {
  if (!page) return <span className="text-[12.5px] text-ink-3">Page not linked</span>;
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1 rounded-control px-1.5 py-0.5 text-[12.5px] font-semibold text-accent ring-1 ring-inset ring-accent/25 transition-colors hover:bg-accent-soft"
      title={`Show page ${page} beside the analysis`}
    >
      <BookOpenText className="h-3.5 w-3.5" strokeWidth={1.75} />
      Page {page}
    </button>
  );
}

/** One line for the points of a section that are held back: why, and a link to the page of the original. */
function Placeholder({ line, onOpen }: { line: PlaceholderLine; onOpen: (page: number, boxes: QuoteBox[]) => void }) {
  const pages = Array.from(new Set(line.pages)).sort((a, b) => a - b);
  const lead = line.state === "waiting_for_team" ? "read" : "Read";
  return (
    <p className="mt-3 rounded-panel bg-sunken px-3.5 py-2.5 text-[14px] leading-relaxed text-ink-2" data-testid="held-back-line" data-state={line.state}>
      {line.before}
      {pages.length === 0 ? (
        <>
          {lead} the{" "}
          <button
            type="button"
            onClick={() => onOpen(1, [])}
            className="font-semibold text-accent underline underline-offset-2 hover:text-accent-strong"
            aria-label="Open the original circular"
          >
            original circular
          </button>
          .
        </>
      ) : (
        <>
          {line.marked ? `${lead} the highlighted lines on ` : `${lead} `}
          {pages.length === 1 ? "page " : "pages "}
          {pages.map((n, i) => (
            <span key={n}>
              {i > 0 && (i === pages.length - 1 ? " and " : ", ")}
              <button
                type="button"
                onClick={() => onOpen(n, line.highlights[n] ?? [])}
                className="font-semibold text-accent underline underline-offset-2 hover:text-accent-strong"
                aria-label={`Open page ${n} of the original`}
              >
                {n}
              </button>
            </span>
          ))}
          {" of the original."}
        </>
      )}
    </p>
  );
}

function readingLine(total: number, waiting: number, r: ReadingStatus | null) {
  const ready = `${total - waiting} of ${total} pages ready`;
  const next =
    r?.analysis_after === "AUTOMATIC"
      ? " The summary and requirements are added by themselves right after."
      : r?.analysis_after === "LATER"
        ? " The summary and requirements for older circulars are added later."
        : " An administrator can run the analysis once all pages are read.";
  if (!r) return `Reading the page images: ${ready}. The text appears here by itself as each page is read.`;
  if (r.state === "PAUSED_DAILY_LIMIT") {
    const at = r.resumes_at ? new Date(r.resumes_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : null;
    return `Page reading is paused: today's free reading limit is used up. It starts again${at ? ` at about ${at}` : " tomorrow"}. ${ready}.${next}`;
  }
  if (r.state === "PAUSED_NO_KEY" || r.state === "PAUSED_NOT_RUNNING")
    return `Page reading is not running right now, so these pages are waiting. ${ready}.${next}`;
  if (r.state === "QUEUED")
    return `Waiting in line: ${r.pages_ahead} pages from newer circulars are read first. ${ready}, ${minutesText(r.minutes_left)} left.${next}`;
  return `Reading the page images: ${ready}, ${minutesText(r.minutes_left)} left. The text appears here by itself as each page is read.${next}`;
}

export default function CircularDetail(props: Props) {
  const {
    doc,
    pages,
    pageNumber,
    setPageNumber,
    pagePanelOpen,
    setPagePanelOpen,
    highlight,
    setHighlight,
    qaQuery,
    setQaQuery,
    qaLoading,
    qaResponse,
    qaMatches,
    qaError,
    onAsk,
    currentUser,
    onSignIn,
    onRefresh,
  } = props;

  const [analyzing, setAnalyzing] = useState(false);
  const [reextracting, setReextracting] = useState(false);
  const [adminMessage, setAdminMessage] = useState<{ type: "success" | "error" | "info"; text: string; canForce?: boolean } | null>(null);

  const isAdmin = !!currentUser?.is_superuser;
  const [addOpen, setAddOpen] = useState(false);
  const [added, setAdded] = useState<{ orgId: string; registerId: string; count: number } | null>(null);
  const rights = useAddRights(!!currentUser);
  const wsState = useWorkspace();
  const status = String(doc.publication_status || "");
  // A circular with a point waiting for a person can still have shown points, so it can be added from.
  const published = status.startsWith("PUBLISHED") || status === "AWAITING_REVIEW";
  const canAddToRegister = !!currentUser && !doc.is_private && published && !!rights.active;
  const activeOrgId = rights.active?.id ?? null;
  useEffect(() => {
    // Preload the bank workspace so the "In your register" tags are right and adding is instant.
    if (canAddToRegister && activeOrgId) void ensureWorkspace(activeOrgId);
  }, [canAddToRegister, activeOrgId]);
  const inYourRegister = (item: ClaimItem) =>
    !!activeOrgId &&
    orgItems(wsState, activeOrgId).some((i) => i.source.document_id === doc.id && ((!!item.obligation_id && i.obligation_id === item.obligation_id) || i.source.quote === item.quote));
  const rel = useRelState();
  const relStatus = rel.status[doc.id];
  const inForce = inForceOf(rel, doc);
  const awaiting = isAdmin
    ? (relStatus?.unconfirmed_incoming.length ?? 0) + (relStatus?.outgoing.filter((l) => l.verification_status === "PENDING_REVIEW").length ?? 0)
    : 0;

  // The checked points of this circular: from the shared copy at once, kept fresh while the page is visible.
  const { view, error: claimsError, loading: claimsLoading, state: claimsState } = useDocClaims(doc.id, isAdmin);

  // In-force status, links and compare targets: shown from the shared copy at once, refreshed in the background.
  useEffect(() => {
    loadStatus(doc.id).catch(() => undefined);
  }, [doc.id, currentUser?.id]);

  const pageCount = doc.versions?.[0]?.page_count ?? pages.length;
  const waitingCount = pages.filter((p) => p.quality_status === "PENDING_VISION").length;
  // What the circular is waiting for and roughly how long: refreshed with every page update and
  // every 10 s while pages wait, so the line below is never stale.
  const [reading, setReading] = useState<ReadingStatus | null>(null);
  useEffect(() => {
    let alive = true;
    const load = () =>
      fetchReadingStatus(doc.id)
        .then((r) => alive && setReading(r))
        .catch(() => undefined);
    void load();
    if (waitingCount === 0) return () => {
      alive = false;
    };
    const t = setInterval(load, 10000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [doc.id, waitingCount]);

  const openPage = (n: number, quote?: string | null, boxes?: QuoteBox[] | null) => {
    setPageNumber(n);
    const hasBoxes = !!boxes && boxes.length > 0;
    setHighlight(quote || hasBoxes ? { text: quote ?? "", boxes: boxes ?? null, key: `${Date.now()}` } : null);
    setPagePanelOpen(true);
  };

  // Analysis runs in the background on the server. While it runs, this page checks every few
  // seconds and redraws itself the moment it ends, so the screen is never stale.
  const finishAnalysis = (state: string, message?: string | null) => {
    setAnalyzing(false);
    if (state === "DONE") {
      setAdminMessage({ type: "success", text: "Analysis finished. Points that passed their checks are shown below; the rest wait for a check." });
      void reloadDoc(doc.id);
      onRefresh();
    } else if (state === "FAILED") {
      setAdminMessage({ type: "error", text: message || "The analysis could not finish. Earlier results are kept." });
    } else if (state === "WAITING_FOR_PAGES") {
      setAdminMessage({ type: "info", text: message || "Some pages are still being read. The analysis can run once they are done." });
    } else if (state === "UNCHANGED") {
      setAdminMessage({ type: "info", text: message || "Nothing changed since the last analysis.", canForce: true });
    }
  };

  useEffect(() => {
    // Pick up a run that is already going (started earlier or by another admin).
    if (!isAdmin) return;
    let cancelled = false;
    fetchAnalysisStatus(doc.id)
      .then((st) => {
        if (cancelled) return;
        if (st.state === "RUNNING") {
          setAnalyzing(true);
          setAdminMessage({ type: "info", text: "Analysing this circular. This page updates by itself when it is done." });
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [doc.id, isAdmin]);

  useEffect(() => {
    if (!analyzing) return;
    let stopped = false;
    const timer = setInterval(async () => {
      try {
        const st = await fetchAnalysisStatus(doc.id);
        if (!stopped && st.state !== "RUNNING") {
          stopped = true;
          clearInterval(timer);
          finishAnalysis(st.state, st.message);
        }
      } catch {
        /* keep checking; a dropped request is not a result */
      }
    }, 2500);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [analyzing, doc.id]);

  const runAnalysis = async (force = false) => {
    setAnalyzing(true);
    setAdminMessage({ type: "info", text: "Analysing this circular. This page updates by itself when it is done." });
    try {
      const st = await triggerDocumentAnalysis(doc.id, { force });
      if (st.state !== "RUNNING") finishAnalysis(st.state, st.message);
    } catch (e: any) {
      setAnalyzing(false);
      setAdminMessage({ type: "error", text: e.message || "Could not start the analysis." });
    }
  };

  const reextract = async () => {
    try {
      setReextracting(true);
      setAdminMessage(null);
      const res = await reextractDocument(doc.id);
      const kept = res.human_corrections_preserved ?? 0;
      setAdminMessage({
        type: "success",
        text: `${res.message} ${kept > 0 ? `${kept} human-corrected page(s) kept their corrected text.` : "No human corrections to keep."}`,
      });
      onRefresh();
    } catch (e: any) {
      setAdminMessage({ type: "error", text: "Re-extraction failed: " + (e.message || String(e)) });
    } finally {
      setReextracting(false);
    }
  };

  // ------------------------------------------------------------------ what the checked view holds
  const counts = view?.counts;
  const itemsOf = (s: ClaimSection): ClaimItem[] => view?.sections[s] ?? [];
  const shownOf = (s: ClaimSection) => itemsOf(s).filter((i) => i.shown !== false);
  const heldOf = (s: ClaimSection) => (isAdmin ? itemsOf(s).filter((i) => i.shown === false) : []);
  const lines = !isAdmin && view ? placeholderLines(view.hidden, view.checking) : [];
  const linesOf = (s: ClaimSection) => lines.filter((l) => l.section === s);
  const anyByTeam = SECTION_ORDER.some((s) => shownOf(s).some((i) => i.checked_by === "TEAM"));
  const badge = view && view.state !== "NO_ANALYSIS" && counts && (status.startsWith("PUBLISHED") || status === "AWAITING_REVIEW") ? checkedBadge(counts, anyByTeam) : null;
  const dateOf = (kind: string) => shownOf("dates").find((i) => i.fields.date_kind === kind)?.fields.date as string | undefined;
  const hasHeld = !!counts && counts.shown < counts.total;

  const pdfButton =
    doc.is_private && !doc.source_url ? (
      <button type="button" onClick={() => openDocumentPdf(doc.id).catch((err) => alert(err.message))} className="btn-secondary">
        <FileDown className="h-4 w-4" strokeWidth={1.75} />
        Open PDF
      </button>
    ) : (
      <a href={doc.source_url || documentPdfUrl(doc.id)} target="_blank" rel="noreferrer" className="btn-secondary">
        <FileDown className="h-4 w-4" strokeWidth={1.75} />
        Original PDF
        <ArrowUpRight className="h-3.5 w-3.5 text-ink-3" />
      </a>
    );

  const askButton = (item: ClaimItem) =>
    isAdmin ? (
      <button
        type="button"
        onClick={() => void askReview(doc.id, item.id)}
        disabled={!!claimsState.busy[item.id]}
        className="inline-flex min-h-9 items-center gap-1 rounded-control px-2 py-0.5 text-[12.5px] font-semibold text-ink-3 ring-1 ring-inset ring-line-strong transition-colors hover:bg-sunken hover:text-ink sm:min-h-0 sm:px-1.5"
        title="Hide this point from readers until our team has decided it"
        data-testid="ask-review"
      >
        <EyeOff className="h-3.5 w-3.5" strokeWidth={1.75} />
        Ask for review
      </button>
    ) : null;

  /** Administrators: a point waiting for a decision says so in plain words and links to its review. */
  const reviewLink = (item: ClaimItem) =>
    isAdmin && (item.status === "WAITING_FOR_PERSON" || item.status === "NOT_SHOWN") ? (
      <Link
        href={`/admin?tab=checks&point=${item.id}`}
        className="inline-flex min-h-9 items-center gap-1 rounded-control px-2 py-0.5 text-[12.5px] font-semibold text-accent ring-1 ring-inset ring-accent/40 transition-colors hover:bg-sunken sm:min-h-0 sm:px-1.5"
        data-testid="review-link"
      >
        Review
      </Link>
    ) : null;

  /** A shown point that still waits for a decision (a link shown only as a mention) says so. */
  const adminState = (item: ClaimItem) =>
    isAdmin && item.shown !== false && item.status === "WAITING_FOR_PERSON" ? (
      <>
        <span className="text-warn" data-testid="admin-point-state">
          {adminStateText(item)}
        </span>
        {reviewLink(item)}
      </>
    ) : null;

  /** The quiet tag, the page link and (administrators) the ask-for-review button under one shown point. */
  const foot = (item: ClaimItem, extra?: React.ReactNode) => (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[13px] text-ink-3">
      <PageLink page={item.page_number} onClick={() => item.page_number && openPage(item.page_number, item.quote, item.quote_boxes)} />
      <span data-testid="checked-tag">{checkedTag(item)}</span>
      {extra}
      {adminState(item)}
      {askButton(item)}
    </div>
  );

  /** A point an administrator can see that readers cannot: its state in plain words. */
  const heldRow = (item: ClaimItem, text: string) => (
    <li key={item.id} className="rounded-panel border border-dashed border-line-strong px-3 py-2 text-[14px] text-ink-2" data-testid="admin-held-point">
      <p className="max-w-prose text-ink" lang={hasBangla(text) ? "bn" : undefined}>
        {text}
      </p>
      <p className="mt-1 text-[13px] text-ink-3" data-testid="admin-point-state">
        {adminStateText(item)}
      </p>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1.5">
        {item.page_number && <PageLink page={item.page_number} onClick={() => openPage(item.page_number!, item.quote, item.quote_boxes)} />}
        {reviewLink(item)}
      </div>
    </li>
  );

  const sectionHint = (s: ClaimSection, empty: string) => {
    if (shownOf(s).length > 0 || heldOf(s).length > 0 || linesOf(s).length > 0) return null;
    return <p className="text-[14.5px] text-ink-3">{empty}</p>;
  };

  const heldPoints = (s: ClaimSection, label: (i: ClaimItem) => string) =>
    heldOf(s).length > 0 && (
      <ul className="mt-3 space-y-2">
        {heldOf(s).map((i) => heldRow(i, label(i)))}
      </ul>
    );

  const placeholders = (s: ClaimSection) =>
    linesOf(s).map((l) => <Placeholder key={l.key} line={l} onOpen={(n, boxes) => openPage(n, "", boxes)} />);

  const bulletList = (s: ClaimSection) =>
    shownOf(s).length > 0 && (
      <ul className="max-w-prose space-y-3">
        {shownOf(s).map((i) => (
          <li key={i.id} className="grid grid-cols-[1rem_1fr] gap-2 text-[15px] leading-relaxed text-ink" data-testid="shown-point">
            <span aria-hidden className="mt-[0.7em] h-1.5 w-1.5 rounded-full bg-accent" />
            <div className="space-y-1.5">
              <span lang={hasBangla(i.fields.text) ? "bn" : undefined}>{i.fields.text}</span>
              {foot(i)}
            </div>
          </li>
        ))}
      </ul>
    );

  const analysisBody = claimsLoading ? (
    <div className="space-y-3 border-t border-line pt-5" aria-busy="true" aria-label="Loading the checked points" role="status">
      <p className="text-[14px] text-ink-3">Loading the checked points of this circular. This takes a second.</p>
      <SkeletonLine className="h-4 w-28" />
      <SkeletonLine className="h-3.5 w-full" />
      <SkeletonLine className="h-3.5 w-11/12" />
      <SkeletonLine className="h-3.5 w-4/5" />
      <SkeletonLine className="mt-6 h-4 w-36" />
      <SkeletonLine className="h-16 w-full" />
    </div>
  ) : !view ? (
    <Notice kind="error">
      Could not load the points of this circular{claimsError ? ` (${claimsError})` : ""}. This page tries again by itself every few seconds.
    </Notice>
  ) : view.state === "NO_ANALYSIS" ? (
    <div className="space-y-3 border-t border-line pt-5">
      {doc.title_bn && (
        <p lang="bn" className="max-w-prose text-[16px] text-ink">
          {doc.title_bn}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-[14px] text-ink-2">No analysis has been run on this circular yet.</span>
        {isAdmin && (
          <button type="button" onClick={() => runAnalysis()} disabled={analyzing} className="btn-secondary py-1">
            <Sparkles className="h-3.5 w-3.5" />
            {analyzing ? "Running..." : "Run analysis"}
          </button>
        )}
      </div>
    </div>
  ) : (
    <div className="space-y-6">
      {view.state === "ANALYSING" && !analyzing && (
        <Notice kind="info">Analysing this circular. This page updates by itself when it is done.</Notice>
      )}
      {hasHeld && counts && (
        <p className="text-[14px] text-ink-2" data-testid="showing-count">
          Showing {counts.shown} of {counts.total} points.
          {isAdmin && counts.waiting_for_team > 0 && ` ${counts.waiting_for_team} waiting for a check.`}
          {isAdmin && counts.not_shown > 0 && ` ${counts.not_shown} not shown.`}
        </p>
      )}
      {isAdmin && counts && counts.checking > 0 && (
        <Notice kind="info">
          {counts.checking} {counts.checking === 1 ? "point is" : "points are"} still being checked against the page image,{" "}
          {view.checking.paused_until
            ? "checking is paused until today's free limit resets."
            : `${minutesText(view.checking.minutes_left)} left. This page updates by itself.`}
        </Notice>
      )}

      <Section title="Summary">
        {bulletList("summary")}
        {heldPoints("summary", (i) => i.fields.text ?? "")}
        {placeholders("summary")}
        {sectionHint("summary", "No summary points are available yet.")}
      </Section>

      <Section title="What has changed">
        {bulletList("changes")}
        {heldPoints("changes", (i) => i.fields.text ?? "")}
        {placeholders("changes")}
        {sectionHint("changes", "No changes to earlier circulars are listed. The requirements below are what this circular asks for.")}
      </Section>

      <Section title="Requirements" count={shownOf("requirements").length}>
        {shownOf("requirements").length > 0 && (
          <ol className="divide-y divide-line">
            {shownOf("requirements").map((item, i) => {
              const f = item.fields;
              return (
                <motion.li
                  key={item.id}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.25, delay: Math.min(i, 8) * 0.03, ease: EASE_OUT }}
                  className="space-y-2.5 py-4 first:pt-0 last:pb-0"
                  data-testid="shown-point"
                >
                  <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1.5">
                    <h4 className="max-w-prose text-[15.5px] font-semibold leading-snug text-ink">{f.title || "Requirement"}</h4>
                    <span className="flex flex-wrap items-center gap-1.5">
                      {inYourRegister(item) && (
                        <span data-testid="in-register-tag">
                          <Tag tone="ok" title="This obligation is already in a register of your bank">
                            In your register
                          </Tag>
                        </span>
                      )}
                      {f.obligation_type && <Tag tone="accent">{readable(f.obligation_type)}</Tag>}
                    </span>
                  </div>
                  {f.description && <p className="max-w-prose text-[15px] leading-relaxed text-ink-2">{f.description}</p>}
                  {item.quote && (
                    <blockquote className="quote max-w-prose" lang={hasBangla(item.quote) ? "bn" : undefined}>
                      &ldquo;{item.quote}&rdquo;
                    </blockquote>
                  )}
                  {foot(
                    item,
                    <>
                      <span>Applies to: {entityLabel(f.who) || "Not stated"}</span>
                      {f.deadline ? (
                        <span className="font-semibold text-warn">Deadline: {formatDate(f.deadline)}</span>
                      ) : f.deadline_text ? (
                        <span className="font-semibold text-warn">Deadline: {f.deadline_text}</span>
                      ) : null}
                    </>
                  )}
                </motion.li>
              );
            })}
          </ol>
        )}
        {heldPoints("requirements", (i) => i.fields.title ?? "Requirement")}
        {placeholders("requirements")}
        {sectionHint("requirements", "No requirements have been extracted for this circular yet.")}
      </Section>

      <Section title="Who it applies to">
        {shownOf("applies_to").length > 0 && (
          <ul className="max-w-prose space-y-2 text-[15px] text-ink">
            {shownOf("applies_to").map((i) => (
              <li key={i.id} className="grid grid-cols-[1rem_1fr] gap-2" data-testid="shown-point">
                <span aria-hidden className="mt-[0.65em] h-1.5 w-1.5 rounded-full bg-ink-3" />
                <div className="space-y-1.5">
                  <span>{entityLabel(i.fields.entity)}</span>
                  {foot(i)}
                </div>
              </li>
            ))}
          </ul>
        )}
        {heldPoints("applies_to", (i) => entityLabel(i.fields.entity))}
        {placeholders("applies_to")}
        {sectionHint("applies_to", "Not identified yet. Read the circular text for who it applies to.")}
      </Section>

      <Section title="Dates">
        <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-3">
          <div>
            <dt className="text-[13px] text-ink-3">Issued</dt>
            <dd className="mt-0.5 text-[15px] font-semibold text-ink tabular-nums">{formatDate(doc.publication_date) || "Not stated"}</dd>
          </div>
          <div>
            <dt className="text-[13px] text-ink-3">Takes effect</dt>
            <dd className="mt-0.5 text-[15px] font-semibold text-ink tabular-nums">{formatDate(dateOf("EFFECTIVE")) || "Not stated"}</dd>
          </div>
          <div>
            <dt className="text-[13px] text-ink-3">Compliance deadline</dt>
            <dd className={`mt-0.5 text-[15px] font-semibold tabular-nums ${dateOf("COMPLIANCE") ? "text-warn" : "text-ink"}`}>
              {formatDate(dateOf("COMPLIANCE")) || "Not stated"}
            </dd>
          </div>
          {dateOf("REPORTING") && (
            <div>
              <dt className="text-[13px] text-ink-3">Reporting deadline</dt>
              <dd className="mt-0.5 text-[15px] font-semibold tabular-nums text-warn">{formatDate(dateOf("REPORTING"))}</dd>
            </div>
          )}
        </dl>
        {shownOf("dates").length > 0 && (
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5">
            {shownOf("dates").map((i) => (
              <span key={i.id} className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] text-ink-3" data-testid="shown-point">
                <PageLink page={i.page_number} onClick={() => i.page_number && openPage(i.page_number, i.quote, i.quote_boxes)} />
                {askButton(i)}
              </span>
            ))}
          </div>
        )}
        {heldPoints("dates", (i) => `${readable(i.fields.date_kind)} date: ${formatDate(i.fields.date) ?? ""}`)}
        {placeholders("dates")}
      </Section>

      <Section title="Exceptions and conditions">
        {shownOf("exemptions").length > 0 && (
          <ul className="max-w-prose space-y-3 text-[15px] text-ink">
            {shownOf("exemptions").map((i) => (
              <li key={i.id} className="grid grid-cols-[1rem_1fr] gap-2" data-testid="shown-point">
                <span aria-hidden className="mt-[0.65em] h-1.5 w-1.5 rounded-full bg-ink-3" />
                <div className="space-y-1.5">
                  <span lang={hasBangla(i.fields.text) ? "bn" : undefined}>{i.fields.text}</span>
                  {foot(i)}
                </div>
              </li>
            ))}
          </ul>
        )}
        {heldPoints("exemptions", (i) => i.fields.text ?? "")}
        {placeholders("exemptions")}
        {sectionHint("exemptions", "No exceptions or special conditions identified yet.")}
      </Section>

      {(shownOf("links").length > 0 || heldOf("links").length > 0 || linesOf("links").length > 0) && (
        <Section title="Related circulars" count={shownOf("links").length}>
          {shownOf("links").length > 0 && (
            <ul className="divide-y divide-line">
              {shownOf("links").map((item) => {
                const link = item.link;
                const label = link?.target_reference || "Cited circular";
                return (
                  <li key={item.id} className="space-y-1.5 py-3 first:pt-0 last:pb-0" data-testid="related-item" data-type={link?.shown_type}>
                    <div className="flex flex-wrap items-center gap-2">
                      {link?.target_document_id ? (
                        <Link href={`/?doc=${link.target_document_id}`} className="refno hover:underline">
                          {label}
                        </Link>
                      ) : (
                        <span className="refno">{label}</span>
                      )}
                      <Tag tone="info">{relLabel(link?.shown_type || "REFERENCES")}</Tag>
                      {!link?.target_document_id && (
                        <Tag tone="muted" title="This circular is not in the library yet">
                          Not in library
                        </Tag>
                      )}
                    </div>
                    {item.quote && (
                      <blockquote className="quote max-w-prose" lang={hasBangla(item.quote) ? "bn" : undefined}>
                        &ldquo;{item.quote}&rdquo;
                      </blockquote>
                    )}
                    {foot(item)}
                  </li>
                );
              })}
            </ul>
          )}
          {heldPoints("links", (i) => i.link?.target_reference || i.fields.target_hint || "Cited circular")}
          {placeholders("links")}
        </Section>
      )}

      <Section title="Ask this circular">
        {currentUser ? (
          <>
            <p className="mb-3 max-w-prose text-[14px] text-ink-3">Answers come only from this circular, with the page each quote is on.</p>
            <form onSubmit={onAsk} className="flex flex-col gap-2 sm:flex-row">
              <label htmlFor={`qa-${doc.id}`} className="sr-only">
                Your question
              </label>
              <input
                id={`qa-${doc.id}`}
                type="text"
                value={qaQuery}
                onChange={(e) => setQaQuery(e.target.value)}
                placeholder="For example: what is the deadline, and who must report?"
                className="field flex-1"
              />
              <button type="submit" disabled={qaLoading || !qaQuery.trim()} className="btn-primary px-4 py-2">
                <Send className="h-4 w-4" strokeWidth={1.75} />
                {qaLoading ? "Searching..." : "Ask"}
              </button>
            </form>

            {qaError && (
              <Notice kind="error" className="mt-3">
                {qaError}
              </Notice>
            )}

            {qaLoading && !qaResponse && (
              <div className="mt-4 space-y-3 rounded-panel border border-line bg-sunken/50 p-4" aria-live="polite">
                <p className="flex items-center gap-2 text-[14px] text-ink-2">
                  <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                  Writing the answer. The matching lines are below already.
                </p>
                {!qaMatches ? (
                  <SkeletonLine />
                ) : qaMatches.length === 0 ? (
                  <p className="text-[13.5px] text-ink-3">No line in this circular uses those exact words. The answer may still find it.</p>
                ) : (
                  <div className="space-y-3 border-t border-line pt-3">
                    <p className="text-[13px] font-semibold text-ink-2">Matching lines</p>
                    {qaMatches.slice(0, 4).map((m, i) => (
                      <div key={i} className="space-y-1.5">
                        <blockquote className="quote" lang={hasBangla(m.verbatim_excerpt) ? "bn" : undefined}>
                          &ldquo;{m.verbatim_excerpt}&rdquo;
                        </blockquote>
                        <PageLink page={m.page_number} onClick={() => openPage(m.page_number, m.verbatim_excerpt, (m.quote_boxes as QuoteBox[]) ?? null)} />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {qaResponse && (
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.25, ease: EASE_OUT }}
                className="mt-4 rounded-panel border border-line bg-sunken/50 p-4"
              >
                <p className="max-w-prose whitespace-pre-line text-[15px] leading-relaxed text-ink">{qaResponse.answer}</p>
                {Array.isArray(qaResponse.citations) && qaResponse.citations.length > 0 && (
                  <div className="mt-4 space-y-3 border-t border-line pt-3">
                    <p className="text-[13px] font-semibold text-ink-2">From the circular</p>
                    {qaResponse.citations.slice(0, 3).map((cit, i) => {
                      const p = cit.page_number || cit.page || 1;
                      const q = cit.verbatim_excerpt || cit.quoted_text || cit.quote || "";
                      return (
                        <div key={i} className="space-y-1.5">
                          <blockquote className="quote" lang={hasBangla(q) ? "bn" : undefined}>
                            &ldquo;{q}&rdquo;
                          </blockquote>
                          <PageLink page={p} onClick={() => openPage(p, q)} />
                        </div>
                      );
                    })}
                  </div>
                )}
              </motion.div>
            )}
          </>
        ) : (
          <div className="flex items-start gap-3 rounded-panel border border-line bg-sunken/60 px-4 py-4">
            <Lock className="mt-0.5 h-4 w-4 shrink-0 text-ink-3" strokeWidth={1.75} />
            <div>
              <p className="max-w-prose text-[14.5px] text-ink-2">Sign in to ask questions about this circular and get answers with the page each quote is on.</p>
              <button type="button" onClick={onSignIn} className="btn-primary mt-3">
                Sign in
              </button>
            </div>
          </div>
        )}
      </Section>
    </div>
  );

  return (
    <article className="rounded-panel border border-line bg-surface shadow-panel">
      {/* Document header */}
      <header className="space-y-3 px-5 pb-5 pt-5 sm:px-7 sm:pt-6">
        <div className="flex flex-wrap items-center gap-2">
          <span className="refno">{doc.reference_number || "Circular"}</span>
          {badge ? (
            <span data-testid="checked-badge">
              <Tag tone={badge.tone} title={badge.hint}>
                <CheckCircle2 className="h-3 w-3" strokeWidth={2} aria-hidden />
                {badge.label}
              </Tag>
            </span>
          ) : (
            <StatusBadge status={doc.publication_status} />
          )}
          <InForceBadge info={inForce} />
          {awaiting > 0 && <AwaitingReviewTag count={awaiting} />}
          {doc.is_private && <PrivateTag />}
        </div>
        <h2 className="max-w-[60ch] text-[22px] font-semibold leading-[1.3] tracking-[-0.01em] text-ink [text-wrap:balance] sm:text-[24px]">
          {titleWithoutRef(doc.title, doc.reference_number)}
        </h2>
        {doc.title_bn && (
          <p lang="bn" className="max-w-[60ch] text-[17px] text-ink-2">
            {doc.title_bn}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-[13.5px] text-ink-3">
          <span>
            Issued <span className="font-semibold text-ink-2 tabular-nums">{formatDate(doc.publication_date)}</span>
          </span>
          {doc.effective_date && (
            <span>
              Effective <span className="font-semibold text-ink-2 tabular-nums">{formatDate(doc.effective_date)}</span>
            </span>
          )}
          <span>{readable(doc.document_type) || "Circular"}</span>
          {pageCount > 0 && <span className="tabular-nums">{pageCount} {pageCount === 1 ? "page" : "pages"}</span>}
          <span>Bangladesh Bank</span>
        </div>
        <div className="flex flex-wrap items-center gap-2 pt-1">
          {pdfButton}
          <Link href={`/circular/${doc.id}/links`} className="btn-secondary" data-testid="history-links-button">
            <GitBranch className="h-4 w-4" strokeWidth={1.75} />
            History &amp; links
          </Link>
          <CompareButtons doc={doc} outgoing={relStatus?.outgoing ?? []} />
          {canAddToRegister && (
            <button type="button" className="btn-secondary" onClick={() => setAddOpen(true)} data-testid="add-to-register-button">
              <ListPlus className="h-4 w-4" strokeWidth={1.75} />
              Add to register
            </button>
          )}
          {pages.length > 0 && (
            <button
              type="button"
              onClick={() => {
                if (pagePanelOpen) {
                  setPagePanelOpen(false);
                } else {
                  setHighlight(null);
                  setPagePanelOpen(true);
                }
              }}
              aria-pressed={pagePanelOpen}
              className={pagePanelOpen ? "btn-secondary border-accent/50 bg-accent-soft text-accent hover:bg-accent-soft" : "btn-secondary"}
            >
              <BookOpenText className="h-4 w-4" strokeWidth={1.75} />
              {pagePanelOpen ? "Hide source pages" : "Source pages"}
            </button>
          )}
        </div>

        {props.viewingVersionId && props.viewingVersionId !== doc.current_version_id && (
          <Notice kind="info">You are viewing an older version of this circular (the one the register item was built from).</Notice>
        )}
        {added && (
          <Notice kind="success" onDismiss={() => setAdded(null)}>
            {added.count} item{added.count === 1 ? "" : "s"} added.{" "}
            <Link href={`/workspace/${added.orgId}/registers/${added.registerId}`} className="font-semibold text-accent underline">
              View register
            </Link>
          </Notice>
        )}
        {waitingCount > 0 && <Notice kind="info">{readingLine(pages.length, waitingCount, reading)}</Notice>}
        {waitingCount === 0 && view?.state === "NO_ANALYSIS" && reading?.analysis_after === "LATER" && (
          <Notice kind="info">
            This is an older circular from the archive. Its full text is here now; the summary and requirements will be added later.
          </Notice>
        )}
        {isAdmin && (
          <div className="mt-2 space-y-2 rounded-panel bg-sunken px-3 py-2.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="mr-1 flex items-center gap-1.5 text-[13px] font-semibold text-ink-2">
                <ShieldCheck className="h-4 w-4" strokeWidth={1.75} />
                Admin
              </span>
              <button type="button" onClick={() => runAnalysis()} disabled={analyzing} className="btn-secondary py-1">
                <RefreshCw className={`h-3.5 w-3.5 ${analyzing ? "animate-spin" : ""}`} />
                {analyzing ? "Analysing..." : "Run analysis"}
              </button>
              <button
                type="button"
                onClick={() => void askReviewAll(doc.id)}
                disabled={!!claimsState.busyDoc[doc.id] || !counts || counts.shown === 0}
                className="btn-secondary py-1"
                title="Hide every shown point from readers until our team has decided each one"
                data-testid="ask-review-all"
              >
                <EyeOff className="h-3.5 w-3.5" />
                Ask for review of all points
              </button>
              <button type="button" onClick={reextract} disabled={reextracting} className="btn-secondary py-1">
                {reextracting ? "Re-extracting..." : "Re-extract pages"}
              </button>
              <Link href="/admin" className="btn-ghost py-1">
                Console
              </Link>
            </div>
            {adminMessage && (
              <Notice kind={adminMessage.type}>
                {adminMessage.text}
                {adminMessage.canForce && (
                  <button type="button" onClick={() => runAnalysis(true)} className="ml-2 font-semibold underline underline-offset-2">
                    Run it again anyway
                  </button>
                )}
              </Notice>
            )}
            {claimsState.notice && (
              <Notice kind={claimsState.notice.kind} onDismiss={clearClaimsNotice}>
                {claimsState.notice.text}
              </Notice>
            )}
          </div>
        )}
      </header>

      <div className={`px-5 pb-7 sm:px-7 ${pagePanelOpen ? "xl:grid xl:grid-cols-[minmax(0,1fr)_minmax(340px,0.9fr)] xl:gap-6" : ""}`}>
        <div className="min-w-0">{analysisBody}</div>
        {pagePanelOpen && (
          <motion.div
            initial={{ opacity: 0, x: 12 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.25, ease: EASE_OUT }}
            className="fixed inset-x-0 bottom-0 z-50 h-[75dvh] px-2 pb-2 xl:sticky xl:top-[72px] xl:z-auto xl:h-[calc(100dvh-96px)] xl:self-start xl:px-0 xl:pb-0"
          >
            <div className="h-full shadow-pop xl:shadow-none">
              <PagePanel
                documentId={doc.id}
                versionId={props.viewingVersionId || doc.current_version_id || doc.versions?.[0]?.id}
                pages={pages}
                pageNumber={pageNumber}
                onPageChange={(n) => {
                  setPageNumber(n);
                  setHighlight(null);
                }}
                onClose={() => setPagePanelOpen(false)}
                highlight={highlight}
                canEdit={!!currentUser?.is_superuser}
                onPageSaved={props.onPageSaved}
              />
            </div>
          </motion.div>
        )}
      </div>
      {canAddToRegister && rights.active && (
        <AddToRegisterModal
          open={addOpen}
          onClose={() => setAddOpen(false)}
          orgId={rights.active.id}
          orgOptions={rights.eligible}
          onOrgChange={(id) => {
            rights.setActive(id);
            rememberOrg(id);
          }}
          initialDocumentId={doc.id}
          onAdded={(registerId, count) => count > 0 && rights.active && setAdded({ orgId: rights.active.id, registerId, count })}
        />
      )}
    </article>
  );
}
