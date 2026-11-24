"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { ArrowRight, Check, ChevronLeft, FileImage, Pencil, RefreshCw, X } from "lucide-react";
import { ClaimItem, ReviewQueue, ReviewRow, triggerDocumentAnalysis } from "@/services/api";
import {
  clearReviewNotice,
  decide,
  ensurePages,
  focusPoint,
  loadCounts,
  loadQueue,
  preloadAhead,
  pageCorrected,
  useClaimsState,
  useReviewPolling,
} from "@/services/claimsStore";
import {
  ENTITY_LABELS,
  FIELDS_OF_KIND,
  FIELD_LABEL,
  FREQUENCY_LABEL,
  KEY_HELP,
  KIND_LABEL,
  LINK_TYPE_LABEL,
  DATE_KIND_LABEL,
  OBLIGATION_TYPE_LABEL,
  REJECT_REASONS,
  REVIEW_TEXT,
  pointDetails,
  pointHeadline,
  readable,
  stateLine,
  type FieldType,
} from "@/services/claimWords";
import PagePanel, { type PageHighlight } from "./PagePanel";
import { Tag } from "./StatusBadge";
import { EmptyState, Modal, ModalHeader, Notice, SkeletonLine, hasBangla } from "./ui";

type Mode = "view" | "fix" | "reject";

interface FixDraft {
  fields: Record<string, string>;
  evidence: string[];
  confirm: boolean;
}

const OPEN_STATES = ["WAITING_FOR_PERSON", "NOT_SHOWN", "CHECKING"];
const ENTITY_OPTIONS = Object.keys(ENTITY_LABELS).filter((k) => k !== "SCHEDULED_COMMERCIAL_BANK");

function draftFrom(row: ReviewRow): FixDraft {
  const fields: Record<string, string> = {};
  for (const spec of FIELDS_OF_KIND[row.claim.kind] ?? []) {
    const v = row.claim.fields?.[spec.key];
    fields[spec.key] = v === null || v === undefined ? "" : String(v);
  }
  return { fields, evidence: [...(row.claim.quote_sentence_ids ?? [])], confirm: false };
}

function optionsFor(type: FieldType, current: string): Array<{ value: string; label: string }> {
  const base: Record<string, string> =
    type === "obligation_type"
      ? OBLIGATION_TYPE_LABEL
      : type === "link_type"
        ? LINK_TYPE_LABEL
        : type === "date_kind"
          ? DATE_KIND_LABEL
          : type === "frequency"
            ? FREQUENCY_LABEL
            : Object.fromEntries(ENTITY_OPTIONS.map((k) => [k, ENTITY_LABELS[k]]));
  const out = Object.entries(base).map(([value, label]) => ({ value, label }));
  if (type === "frequency" || type === "entity") out.unshift({ value: "", label: type === "entity" ? "Not named" : "Not stated" });
  if (current && !out.some((o) => o.value === current)) out.push({ value: current, label: readable(current) });
  return out;
}

/** A button label with its key shown quietly beside it (desktop only). */
function KeyHint({ k }: { k: string }) {
  return <kbd className="hidden rounded border border-current/30 px-1 text-[11px] font-semibold opacity-70 lg:inline">{k}</kbd>;
}

export default function ClaimReview({ initialPointId }: { initialPointId?: string | null }) {
  const s = useClaimsState();
  const [filter, setFilter] = useState<ReviewQueue>("REQUIRED");
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [modeState, setModeState] = useState<{ id: string | null; mode: Mode }>({ id: null, mode: "view" });
  const [help, setHelp] = useState(false);
  const [pageOpen, setPageOpen] = useState(false);
  const [editRequest, setEditRequest] = useState(0);
  const [panelPageFor, setPanelPageFor] = useState<{ id: string; n: number } | null>(null);
  const [drafts, setDrafts] = useState<Record<string, FixDraft>>({});
  const [problems, setProblems] = useState<Record<string, string[]>>({});
  const [rejectOther, setRejectOther] = useState(false);
  const [rejectNote, setRejectNote] = useState("");
  const [localNotice, setLocalNotice] = useState<string | null>(null);
  const lastAt = useRef(0);

  useReviewPolling(true, 15000, filter);
  // The other list is read once so its count and first points are ready when the filter changes.
  useEffect(() => {
    const other: ReviewQueue = filter === "REQUIRED" ? "OPTIONAL" : "REQUIRED";
    if (!s.queue[other].loaded && !s.queue[other].loading) void loadQueue(other);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter]);

  const queue = s.queue[filter];
  const items = queue.items;
  const found = currentId ? items.findIndex((r) => r.claim.id === currentId) : -1;
  // If the point we were on is gone (decided by somebody else), stay at the same place in the list.
  const at = items.length === 0 ? -1 : found >= 0 ? found : Math.min(lastAt.current, items.length - 1);
  const current: ReviewRow | null = at >= 0 ? items[at] : null;
  const currentKey = current?.claim.id ?? null;
  // The form that is open belongs to one point; moving to another point shows the plain view.
  const currentKeyRef = useRef<string | null>(null);
  currentKeyRef.current = currentKey;
  const mode: Mode = modeState.id === currentKey ? modeState.mode : "view";
  const setMode = useCallback((m: Mode, id?: string | null) => setModeState({ id: id === undefined ? currentKeyRef.current : id, mode: m }), []);

  useEffect(() => {
    if (at >= 0) lastAt.current = at;
    if (currentKey && currentKey !== currentId) setCurrentId(currentKey);
  }, [at, currentKey, currentId]);

  // Opening a different point starts with the plain view and the page of its quote.
  useEffect(() => {
    setRejectOther(false);
    setRejectNote("");
    setLocalNotice(null);
  }, [currentKey]);

  // The next points, their page lists and their page images are fetched ahead.
  useEffect(() => {
    preloadAhead(filter, currentKey);
  }, [filter, currentKey, items.length]);

  // `?point=<id>` (from the circular page) opens that point.
  const openedFor = useRef<string | null>(null);
  useEffect(() => {
    if (!initialPointId || openedFor.current === initialPointId) return;
    openedFor.current = initialPointId;
    void focusPoint(initialPointId).then((row) => {
      if (!row) return setLocalNotice(REVIEW_TEXT.notFound);
      if (!OPEN_STATES.includes(row.claim.status ?? "")) {
        setLocalNotice(`${REVIEW_TEXT.alreadyDecided} ${stateLine(row.claim)}.`.trim());
        return;
      }
      setFilter(row.claim.review_queue === "OPTIONAL" ? "OPTIONAL" : "REQUIRED");
      setCurrentId(row.claim.id);
    });
  }, [initialPointId]);

  // A point that could not be saved comes back: go to it.
  const notice = s.reviewNotice;
  useEffect(() => {
    if (notice?.claimId && notice.kind === "error") {
      const where = (["REQUIRED", "OPTIONAL"] as ReviewQueue[]).find((q) => s.queue[q].items.some((r) => r.claim.id === notice.claimId));
      if (where) {
        setFilter(where);
        setCurrentId(notice.claimId);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [notice]);

  const claim: ClaimItem | null = current?.claim ?? null;
  const open = !!claim && OPEN_STATES.includes(claim.status ?? "");
  const pagesKey = current?.version_id ? `${current.circular.id}:${current.version_id}` : null;
  const pages = pagesKey ? s.pageLists[pagesKey] : undefined;
  useEffect(() => {
    if (current?.version_id) void ensurePages(current.circular.id, current.version_id);
  }, [current?.circular.id, current?.version_id]);
  const panelPage = claim && panelPageFor?.id === claim.id ? panelPageFor.n : current?.page?.page_number ?? 1;
  const highlight = useMemo<PageHighlight | null>(
    () => (claim ? { text: claim.quote || "", boxes: claim.quote_boxes ?? null, key: claim.id } : null),
    [claim]
  );

  // ---------------------------------------------------------------- actions (each reacts at once)

  const moveTo = (delta: number) => {
    const n = items[at + delta];
    if (n) setCurrentId(n.claim.id);
  };

  const run = useCallback(
    (action: "approve" | "fix" | "reject", body: Parameters<typeof decide>[2] = {}) => {
      if (!current || !open) return;
      const row = current;
      const next = items[at + 1] ?? items[at - 1] ?? null;
      // Move on at once; the save runs after.
      setCurrentId(next ? next.claim.id : null);
      setMode("view");
      setRejectOther(false);
      void decide(row.claim.id, action, body).then((res) => {
        if (res.ok) {
          setDrafts((d) => {
            const { [row.claim.id]: _gone, ...rest } = d;
            return rest;
          });
          setProblems((p) => {
            const { [row.claim.id]: _gone, ...rest } = p;
            return rest;
          });
          return;
        }
        if (res.reason === "problem") {
          setProblems((p) => ({ ...p, [row.claim.id]: res.problems }));
          setCurrentId(row.claim.id);
          setMode("fix", row.claim.id);
        } else if (res.reason === "failed") {
          setCurrentId(row.claim.id);
        }
      });
    },
    [current, open, items, at, setMode]
  );

  const startFix = () => {
    if (!current || !open) return;
    setDrafts((d) => (d[current.claim.id] ? d : { ...d, [current.claim.id]: draftFrom(current) }));
    setMode("fix");
  };

  const saveFix = () => {
    if (!current) return;
    const d = drafts[current.claim.id] ?? draftFrom(current);
    run("fix", { fields: d.fields, evidence_ids: d.evidence, confirm_checked: d.confirm });
  };

  const startReject = () => {
    if (!current || !open) return;
    setMode("reject");
    setRejectOther(false);
  };

  const reject = (reason: string) => {
    if (reason === "OTHER" && !rejectOther) {
      setRejectOther(true);
      return;
    }
    run("reject", { reason, note: reason === "OTHER" ? rejectNote.trim() || undefined : undefined });
  };

  // ---------------------------------------------------------------- keys

  const keys = useRef({ run, startFix, startReject, saveFix, reject, moveTo, mode, help, rejectOther });
  keys.current = { run, startFix, startReject, saveFix, reject, moveTo, mode, help, rejectOther };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const k = keys.current;
      const t = e.target as HTMLElement | null;
      const typing = !!t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable);
      if (e.key === "Escape") {
        if (k.help) setHelp(false);
        else if (k.mode !== "view") setMode("view");
        return;
      }
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
        if (k.mode === "fix") {
          e.preventDefault();
          k.saveFix();
        } else if (k.mode === "reject" && k.rejectOther) {
          e.preventDefault();
          k.reject("OTHER");
        }
        return;
      }
      if (typing || e.ctrlKey || e.metaKey || e.altKey) return;
      if (k.help) {
        if (e.key === "?") setHelp(false);
        return;
      }
      switch (e.key.toLowerCase()) {
        case "a":
          if (k.mode === "view") k.run("approve");
          break;
        case "f":
          if (k.mode === "view") {
            e.preventDefault();
            k.startFix();
          }
          break;
        case "r":
          if (k.mode === "view") k.startReject();
          break;
        case "j":
        case "arrowright":
          k.moveTo(1);
          break;
        case "k":
        case "arrowleft":
          k.moveTo(-1);
          break;
        case "?":
          setHelp(true);
          break;
        default:
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setMode]);

  // ---------------------------------------------------------------- the circulars with nothing to show

  const [reruns, setReruns] = useState<Record<string, "running" | "started" | "failed">>({});
  const rerun = (id: string) => {
    setReruns((r) => ({ ...r, [id]: "running" }));
    triggerDocumentAnalysis(id, { force: true })
      .then(() => {
        setReruns((r) => ({ ...r, [id]: "started" }));
        void loadCounts();
      })
      .catch(() => setReruns((r) => ({ ...r, [id]: "failed" })));
  };
  const empty = s.counts?.empty_circulars ?? [];

  // ---------------------------------------------------------------- drawing

  const requiredCount = s.counts?.required ?? s.queue.REQUIRED.total;
  const optionalCount = s.counts?.optional ?? s.queue.OPTIONAL.total;
  const draft = claim ? drafts[claim.id] : undefined;
  const claimProblems = claim ? problems[claim.id] ?? [] : [];

  const filterButton = (id: ReviewQueue, label: string, n: number) => (
    <button
      key={id}
      type="button"
      onClick={() => {
        setFilter(id);
        setCurrentId(null);
        lastAt.current = 0;
      }}
      aria-pressed={filter === id}
      data-testid={`filter-${id.toLowerCase()}`}
      className={`min-h-[44px] flex-1 rounded-control px-3 text-[14px] font-semibold transition-colors sm:min-h-9 sm:flex-none ${
        filter === id ? "bg-surface text-ink shadow-[0_1px_2px_rgb(var(--shadow)/0.12)]" : "text-ink-3 hover:text-ink"
      }`}
    >
      {label} ({n})
    </button>
  );

  const waiting = !queue.loaded && !queue.error;

  const pointCard = current && claim && (
    <div className="panel min-w-0 space-y-4 p-4 sm:p-5" data-testid="review-point" data-point-id={claim.id}>
      <div className="flex flex-wrap items-center gap-2 text-[13px] text-ink-3">
        <span className="tabular-nums" data-testid="review-position">
          {at + 1} of {Math.max(items.length, queue.total)}
        </span>
        <Tag tone={claim.review_queue === "OPTIONAL" || filter === "OPTIONAL" ? "muted" : "warn"}>{filter === "OPTIONAL" ? "Optional" : "Needs a decision"}</Tag>
        {claim.is_high_stakes && <Tag tone="bad">Important</Tag>}
        {!open && <Tag tone="info">{stateLine(claim) || "Already decided"}</Tag>}
      </div>

      <div>
        <p className="text-[13px] text-ink-3">
          <Link href={`/?doc=${current.circular.id}`} className="refno hover:underline">
            {current.circular.reference_number || "Circular"}
          </Link>
          <span className="ml-2">{current.circular.title}</span>
        </p>
        <p className="mt-3 text-[12.5px] font-semibold uppercase tracking-wide text-ink-3">{KIND_LABEL[claim.kind] ?? readable(claim.kind)}</p>
        <p className="mt-0.5 max-w-prose text-[18px] font-semibold leading-snug text-ink" lang={hasBangla(pointHeadline(claim)) ? "bn" : undefined} data-testid="review-headline">
          {pointHeadline(claim)}
        </p>
        {pointDetails(claim).length > 0 && (
          <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-[14px]">
            {pointDetails(claim).map((d) => (
              <div key={d.label} className="contents">
                <dt className="text-ink-3">{d.label}</dt>
                <dd className="text-ink" lang={hasBangla(d.value) ? "bn" : undefined}>
                  {d.value}
                </dd>
              </div>
            ))}
          </dl>
        )}
      </div>

      {(claim.why ?? []).length > 0 && (
        <div>
          <p className="text-[13px] font-semibold text-ink">Why it is here</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-[14px] text-ink-2" data-testid="review-why">
            {(claim.why ?? []).map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <p className="text-[13px] font-semibold text-ink">{claim.page_number ? `Quote (page ${claim.page_number})` : "Quote"}</p>
        {claim.quote ? (
          <blockquote className="quote mt-1 max-w-prose" lang={hasBangla(claim.quote) ? "bn" : undefined} data-testid="review-quote">
            &ldquo;{claim.quote}&rdquo;
          </blockquote>
        ) : (
          <p className="mt-1 text-[14px] text-ink-3">This point does not name a sentence. Read the page on the right and tick the sentence when you fix it.</p>
        )}
        {current.second_reading && (
          <p className="mt-2 max-w-prose text-[14px] text-ink-2" lang={hasBangla(current.second_reading) ? "bn" : undefined}>
            <span className="font-semibold text-ink">Second reading said: </span>
            {current.second_reading}
            <button
              type="button"
              onClick={() => {
                setPageOpen(true);
                setEditRequest((n) => n + 1);
              }}
              className="ml-2 inline-flex min-h-[44px] items-center font-semibold text-accent underline underline-offset-2 sm:min-h-0"
              data-testid="fix-page-reading"
            >
              Fix the page reading
            </button>
          </p>
        )}
        <button type="button" onClick={() => setPageOpen((v) => !v)} className="btn-secondary mt-3 min-h-[44px] lg:hidden" aria-expanded={pageOpen} data-testid="toggle-page">
          <FileImage className="h-4 w-4" strokeWidth={1.75} />
          {pageOpen ? "Hide the page" : `Show page ${panelPage}`}
        </button>
      </div>

      {mode === "fix" && draft && open && (
        <FixForm row={current} draft={draft} problems={claimProblems} onChange={(next) => setDrafts((d) => ({ ...d, [claim.id]: next }))} onSave={saveFix} onCancel={() => setMode("view")} />
      )}

      {mode === "reject" && open && (
        <div className="space-y-2 rounded-panel border border-line p-3" data-testid="reject-form">
          <p className="text-[13px] font-semibold text-ink">Why is it being rejected?</p>
          <div className="flex flex-wrap gap-2">
            {REJECT_REASONS.map((r) => (
              <button
                key={r.id}
                type="button"
                onClick={() => reject(r.id)}
                aria-pressed={r.id === "OTHER" && rejectOther}
                className="btn-secondary min-h-[44px] sm:min-h-9"
                data-testid={`reject-${r.id.toLowerCase()}`}
              >
                {r.label}
              </button>
            ))}
          </div>
          {rejectOther && (
            <div className="space-y-2">
              <label className="block text-[13px] text-ink-3" htmlFor="reject-note">
                What is wrong with it?
              </label>
              <textarea id="reject-note" value={rejectNote} onChange={(e) => setRejectNote(e.target.value)} rows={3} autoFocus className="field text-[16px] sm:text-[14px]" />
              <div className="flex gap-2">
                <button type="button" onClick={() => reject("OTHER")} className="btn-danger min-h-[44px] sm:min-h-9">
                  Reject <KeyHint k="Ctrl+Enter" />
                </button>
                <button type="button" onClick={() => setMode("view")} className="btn-secondary min-h-[44px] sm:min-h-9">
                  Cancel
                </button>
              </div>
            </div>
          )}
          {!rejectOther && (
            <button type="button" onClick={() => setMode("view")} className="btn-ghost min-h-[44px] sm:min-h-9">
              Cancel <KeyHint k="Esc" />
            </button>
          )}
        </div>
      )}

      {mode === "view" && (
        <div className="hidden flex-wrap items-center gap-2 lg:flex" data-testid="review-actions">
          <button type="button" onClick={() => run("approve")} disabled={!open} className="btn-primary" data-testid="approve" aria-keyshortcuts="A">
            <Check className="h-4 w-4" strokeWidth={2.25} />
            Approve <KeyHint k="A" />
          </button>
          <button type="button" onClick={startFix} disabled={!open} className="btn-secondary" data-testid="fix" aria-keyshortcuts="F">
            <Pencil className="h-4 w-4" strokeWidth={1.75} />
            Fix <KeyHint k="F" />
          </button>
          <button type="button" onClick={startReject} disabled={!open} className="btn-danger" data-testid="reject" aria-keyshortcuts="R">
            <X className="h-4 w-4" strokeWidth={2.25} />
            Reject <KeyHint k="R" />
          </button>
          <span className="mx-1 h-5 w-px bg-line" aria-hidden />
          <button type="button" onClick={() => moveTo(-1)} disabled={at <= 0} className="btn-ghost" data-testid="back" aria-keyshortcuts="K">
            <ChevronLeft className="h-4 w-4" />
            Back <KeyHint k="K" />
          </button>
          <button type="button" onClick={() => moveTo(1)} disabled={at >= items.length - 1} className="btn-ghost" data-testid="skip" aria-keyshortcuts="J">
            Skip <ArrowRight className="h-4 w-4" />
            <KeyHint k="J" />
          </button>
        </div>
      )}
    </div>
  );

  return (
    <section className="space-y-4 pb-24 lg:pb-0" data-testid="claim-review">
      <div className="panel flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5">
        <div>
          <h2 className="text-[17px] font-semibold text-ink">Points to check</h2>
          <p className="mt-0.5 max-w-prose text-[14px] text-ink-3">
            Points that did not pass their checks, or that change which rule is in force. Read the quote against the page, then decide.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex flex-1 gap-1 rounded-panel bg-sunken p-1 sm:flex-none" role="group" aria-label="Which points">
            {filterButton("REQUIRED", "Needs a decision", requiredCount)}
            {filterButton("OPTIONAL", "Optional", optionalCount)}
          </div>
          <button type="button" onClick={() => setHelp(true)} className="btn-ghost hidden h-9 w-9 p-0 lg:inline-flex" aria-label="Show the keys" title="Show the keys (?)" data-testid="help">
            ?
          </button>
        </div>
      </div>

      {empty.length > 0 && (
        <details className="rounded-panel border border-line px-4 py-2 text-[14px] text-ink-2" data-testid="empty-circulars">
          <summary className="min-h-[44px] cursor-pointer py-2.5 font-semibold text-ink sm:min-h-0 sm:py-0">
            Circulars with nothing to show ({empty.length})
          </summary>
          <ul className="mt-2 space-y-1.5 pb-1">
            {empty.map((c) => (
              <li key={c.id} className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <Link href={`/?doc=${c.id}`} className="refno min-w-0 hover:underline">
                  {c.reference_number || c.title}
                </Link>
                <button type="button" onClick={() => rerun(c.id)} disabled={reruns[c.id] === "running"} className="inline-flex min-h-9 items-center gap-1 font-semibold text-accent hover:underline disabled:opacity-60">
                  <RefreshCw className={`h-3.5 w-3.5 ${reruns[c.id] === "running" ? "animate-spin" : ""}`} />
                  Run analysis again
                </button>
                {reruns[c.id] === "started" && <span className="text-ink-3">Started. This list updates by itself.</span>}
                {reruns[c.id] === "failed" && <span className="text-bad">Could not start it. Try again in a moment.</span>}
              </li>
            ))}
          </ul>
        </details>
      )}

      {(notice || localNotice) && (
        <Notice kind={notice?.kind === "error" ? "error" : "info"} onDismiss={() => (notice ? clearReviewNotice() : setLocalNotice(null))}>
          <span data-testid="review-notice">{notice?.text ?? localNotice}</span>
        </Notice>
      )}

      {queue.error === "load" && !queue.loaded && (
        <Notice kind="error">
          {REVIEW_TEXT.loadFailed}{" "}
          <button type="button" className="font-semibold underline" onClick={() => void loadQueue(filter)}>
            Try again
          </button>
        </Notice>
      )}

      {waiting ? (
        <div className="space-y-3" aria-busy="true" role="status" data-testid="review-loading">
          <p className="text-[14px] text-ink-3">{REVIEW_TEXT.loading}</p>
          <SkeletonLine className="h-40 w-full" />
        </div>
      ) : !current || !claim ? (
        queue.loaded && (
          <div className="panel p-5" data-testid="review-empty">
            <EmptyState title={filter === "REQUIRED" ? "All caught up" : "Nothing optional"}>{filter === "REQUIRED" ? REVIEW_TEXT.empty : REVIEW_TEXT.emptyOptional}</EmptyState>
          </div>
        )
      ) : (
        <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-2 lg:items-start">
          {pointCard}
          <div className={`${pageOpen ? "block" : "hidden"} h-[72vh] min-w-0 lg:sticky lg:top-4 lg:block lg:h-[calc(100vh-7rem)] lg:has-[[data-fullscreen]]:z-[70]`} data-testid="review-page">
            {pages && current.version_id ? (
              <PagePanel
                documentId={current.circular.id}
                versionId={current.version_id}
                pages={pages}
                pageNumber={panelPage}
                onPageChange={(n) => setPanelPageFor({ id: claim.id, n })}
                onClose={() => setPageOpen(false)}
                highlight={highlight}
                canEdit
                editRequest={editRequest}
                onPageSaved={(p) => pageCorrected(current.circular.id, current.version_id ?? undefined, p)}
              />
            ) : (
              <div className="panel space-y-3 p-4" aria-busy="true">
                <SkeletonLine className="h-5 w-24" />
                <SkeletonLine className="h-64 w-full" />
              </div>
            )}
          </div>
        </div>
      )}

      {/* Phone: the buttons stay at the bottom of the screen. */}
      {current && claim && mode === "view" && (
        <div className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-surface px-3 py-2 lg:hidden" data-testid="review-bar">
          <div className="mx-auto grid max-w-xl grid-cols-4 gap-2">
            <button type="button" onClick={() => run("approve")} disabled={!open} className="btn-primary min-h-[44px] justify-center px-2" data-testid="bar-approve">
              Approve
            </button>
            <button type="button" onClick={startFix} disabled={!open} className="btn-secondary min-h-[44px] justify-center px-2" data-testid="bar-fix">
              Fix
            </button>
            <button type="button" onClick={startReject} disabled={!open} className="btn-danger min-h-[44px] justify-center px-2" data-testid="bar-reject">
              Reject
            </button>
            <button type="button" onClick={() => moveTo(1)} disabled={at >= items.length - 1} className="btn-ghost min-h-[44px] justify-center px-2" data-testid="bar-skip">
              Skip
            </button>
          </div>
        </div>
      )}

      <Modal open={help} onClose={() => setHelp(false)} labelledBy="review-keys-title" width="max-w-md">
        <ModalHeader id="review-keys-title" title="Keys" subtitle="Keys do nothing while you are typing in a box." onClose={() => setHelp(false)} />
        <dl className="grid grid-cols-[auto_1fr] gap-x-5 gap-y-2 p-5 text-[14px]" data-testid="key-list">
          {KEY_HELP.map((k) => (
            <div key={k.keys} className="contents">
              <dt>
                <kbd className="rounded border border-line-strong bg-sunken px-1.5 py-0.5 text-[12.5px] font-semibold text-ink">{k.keys}</kbd>
              </dt>
              <dd className="text-ink-2">{k.what}</dd>
            </div>
          ))}
        </dl>
      </Modal>
    </section>
  );
}

// ------------------------------------------------------------------------------------ the fix form

function FixForm({
  row,
  draft,
  problems,
  onChange,
  onSave,
  onCancel,
}: {
  row: ReviewRow;
  draft: FixDraft;
  problems: string[];
  onChange: (d: FixDraft) => void;
  onSave: () => void;
  onCancel: () => void;
}) {
  const specs = FIELDS_OF_KIND[row.claim.kind] ?? [];
  const setField = (key: string, value: string) => onChange({ ...draft, fields: { ...draft.fields, [key]: value } });
  const toggle = (id: string) =>
    onChange({ ...draft, evidence: draft.evidence.includes(id) ? draft.evidence.filter((x) => x !== id) : [...draft.evidence, id] });
  const input = "field text-[16px] sm:text-[14px]";
  return (
    <form
      className="space-y-3 rounded-panel border border-line p-3"
      onSubmit={(e) => {
        e.preventDefault();
        onSave();
      }}
      data-testid="fix-form"
    >
      <p className="text-[13px] font-semibold text-ink">Fix this point</p>
      {specs.map((spec) => {
        const id = `fix-${spec.key}`;
        const value = draft.fields[spec.key] ?? "";
        return (
          <div key={spec.key}>
            <label htmlFor={id} className="mb-1 block text-[13px] text-ink-3">
              {FIELD_LABEL[spec.key] ?? readable(spec.key)}
            </label>
            {spec.type === "longtext" ? (
              <textarea id={id} value={value} onChange={(e) => setField(spec.key, e.target.value)} rows={3} lang={hasBangla(value) ? "bn" : undefined} className={input} />
            ) : spec.type === "date" ? (
              <input id={id} type="date" value={value} onChange={(e) => setField(spec.key, e.target.value)} className={input} />
            ) : spec.type === "text" ? (
              <input id={id} type="text" value={value} onChange={(e) => setField(spec.key, e.target.value)} lang={hasBangla(value) ? "bn" : undefined} className={input} />
            ) : (
              <select id={id} value={value} onChange={(e) => setField(spec.key, e.target.value)} className={input}>
                {optionsFor(spec.type, value).map((o) => (
                  <option key={o.value || "none"} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            )}
          </div>
        );
      })}

      <fieldset>
        <legend className="mb-1 text-[13px] text-ink-3">Sentences this point comes from</legend>
        <ul className="max-h-56 space-y-1 overflow-y-auto rounded-control border border-line p-2" data-testid="sentence-picker">
          {row.sentences.map((st) => (
            <li key={st.sentence_id}>
              <label className="flex min-h-[44px] cursor-pointer items-start gap-2 rounded px-1 py-1 text-[14px] hover:bg-sunken sm:min-h-0">
                <input type="checkbox" checked={draft.evidence.includes(st.sentence_id)} onChange={() => toggle(st.sentence_id)} className="mt-1 h-4 w-4" />
                <span className="text-ink" lang={hasBangla(st.text) ? "bn" : undefined}>
                  <span className="mr-1 text-ink-3">Page {st.page_number}.</span>
                  {st.text}
                </span>
              </label>
            </li>
          ))}
          {row.sentences.length === 0 && <li className="text-[14px] text-ink-3">No sentences are stored for this page.</li>}
        </ul>
      </fieldset>

      {problems.length > 0 && (
        <div className="space-y-2" data-testid="fix-problems">
          <Notice kind="warning">
            <p className="font-semibold">The checks do not pass with these values:</p>
            <ul className="mt-1 list-disc space-y-0.5 pl-4">
              {problems.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          </Notice>
          <label className="flex min-h-[44px] cursor-pointer items-center gap-2 text-[14px] text-ink sm:min-h-0">
            <input type="checkbox" checked={draft.confirm} onChange={(e) => onChange({ ...draft, confirm: e.target.checked })} className="h-4 w-4" data-testid="confirm-checked" />
            I checked this against the page image
          </label>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <button type="submit" className="btn-primary min-h-[44px] sm:min-h-9" data-testid="save-fix">
          Save the fix <KeyHint k="Ctrl+Enter" />
        </button>
        <button type="button" onClick={onCancel} className="btn-secondary min-h-[44px] sm:min-h-9">
          Cancel <KeyHint k="Esc" />
        </button>
      </div>
    </form>
  );
}
