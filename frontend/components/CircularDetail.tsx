"use client";

import { useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowUpRight, BookOpenText, FileDown, Lock, RefreshCw, Send, ShieldCheck, Sparkles } from "lucide-react";
import {
  AuthUser,
  DocumentAnalysisData,
  DocumentItem,
  DocumentPage,
  ObligationItem,
  QuoteBox,
  RelationshipItem,
  documentPdfUrl,
  openDocumentPdf,
  reextractDocument,
  reviewDocumentAnalysis,
  triggerDocumentAnalysis,
} from "@/services/api";
import StatusBadge, { PrivateTag, Tag } from "./StatusBadge";
import PagePanel, { type PageHighlight } from "./PagePanel";
import { EASE_OUT, Notice, SkeletonLine, hasBangla, titleWithoutRef } from "./ui";

export interface QaResponse {
  answer: string;
  is_grounded?: boolean;
  citations?: Array<{ page_number?: number; page?: number; verbatim_excerpt?: string; quoted_text?: string; quote?: string }>;
}

interface Props {
  doc: DocumentItem;
  analysis: DocumentAnalysisData | null;
  obligations: ObligationItem[];
  relationships: RelationshipItem[];
  pages: DocumentPage[];
  detailLoading: boolean;
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
  qaError: string | null;
  onAsk: (e: React.FormEvent) => void;
  currentUser: AuthUser | null;
  onSignIn: () => void;
  onRefresh: () => void;
}

const ENTITY_LABELS: Record<string, string> = {
  SCHEDULED_COMMERCIAL_BANK: "All scheduled commercial banks in Bangladesh",
  ISLAMIC_BANK: "Islamic Shariah-based scheduled banks",
  NBFI: "Non-bank financial institutions (NBFIs)",
  PAYMENT_SERVICE_PROVIDER: "Payment service providers (PSPs)",
};

function readable(raw?: string) {
  if (!raw) return "";
  const s = raw.replace(/_/g, " ").toLowerCase();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function formatDate(value?: string | null) {
  if (!value) return null;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

function keyChanges(analysis: DocumentAnalysisData | null): string[] {
  const raw: unknown = analysis?.key_changes;
  if (Array.isArray(raw)) return raw.map((c) => (typeof c === "string" ? c : JSON.stringify(c)));
  if (typeof raw === "string") {
    try {
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed.map((c) => (typeof c === "string" ? c : JSON.stringify(c))) : [raw];
    } catch {
      return [raw];
    }
  }
  return [];
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

function PageLink({ page, onClick }: { page?: number; onClick: () => void }) {
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

export default function CircularDetail(props: Props) {
  const {
    doc,
    analysis,
    obligations,
    relationships,
    pages,
    detailLoading,
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
    qaError,
    onAsk,
    currentUser,
    onSignIn,
    onRefresh,
  } = props;

  const [analyzing, setAnalyzing] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [reextracting, setReextracting] = useState(false);
  const [adminMessage, setAdminMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const isAdmin = !!currentUser?.is_superuser;
  const pageCount = doc.versions?.[0]?.page_count ?? pages.length;

  const openPage = (n: number, quote?: string | null, boxes?: QuoteBox[] | null) => {
    setPageNumber(n);
    setHighlight(quote ? { text: quote, boxes: boxes ?? null, key: `${Date.now()}` } : null);
    setPagePanelOpen(true);
  };

  const runAnalysis = async () => {
    try {
      setAnalyzing(true);
      setAdminMessage(null);
      await triggerDocumentAnalysis(doc.id, "gemini");
      setAdminMessage({ type: "success", text: "Analysis finished. The circular now needs a human sign-off." });
      onRefresh();
    } catch (e: any) {
      setAdminMessage({ type: "error", text: "Analysis failed: " + (e.message || String(e)) });
    } finally {
      setAnalyzing(false);
    }
  };

  const signOff = async () => {
    try {
      setPublishing(true);
      setAdminMessage(null);
      const res = await reviewDocumentAnalysis(doc.id, "PUBLISHED_HUMAN_REVIEWED", "Signed off by administrator");
      setAdminMessage({ type: "success", text: res?.message || `Status updated to ${res?.publication_status}.` });
      onRefresh();
    } catch (e: any) {
      setAdminMessage({ type: "error", text: "Sign-off failed: " + (e.message || String(e)) });
    } finally {
      setPublishing(false);
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

  const changes = keyChanges(analysis);
  const payload = analysis?.structured_payload ?? {};
  const covered = payload?.applicability?.covered_entities;
  const conditional = payload?.applicability?.conditional_rules;
  const exemptions = payload?.applicability?.exemptions;
  const effective = payload?.deadlines?.effective_date || doc.effective_date;
  const complianceDeadline = payload?.deadlines?.compliance_deadline || obligations.find((o) => o.explicit_deadline)?.explicit_deadline;

  const appliesTo = (() => {
    if (Array.isArray(covered) && covered.length > 0) return covered.map((e: string) => ENTITY_LABELS[e] || readable(e));
    const targets = Array.from(new Set(obligations.map((o) => o.applicability_summary).filter(Boolean)));
    return targets;
  })();

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

  const analysisBody = !currentUser ? (
    <div className="rounded-panel border border-line bg-sunken/60 px-5 py-6 sm:px-6">
      <div className="flex items-start gap-3">
        <Lock className="mt-0.5 h-5 w-5 shrink-0 text-ink-3" strokeWidth={1.75} />
        <div>
          <h3 className="text-[16px] font-semibold text-ink">Sign in to read the analysis</h3>
          <p className="mt-1 max-w-prose text-[14.5px] leading-relaxed text-ink-2">
            The summary, the requirements with their quotes, who the circular applies to, its dates, and questions answered from its pages are
            available to signed-in users.
          </p>
          <button type="button" onClick={onSignIn} className="btn-primary mt-4">
            Sign in
          </button>
        </div>
      </div>
    </div>
  ) : detailLoading ? (
    <div className="space-y-3 border-t border-line pt-5" aria-busy="true" aria-label="Loading analysis">
      <SkeletonLine className="h-4 w-28" />
      <SkeletonLine className="h-3.5 w-full" />
      <SkeletonLine className="h-3.5 w-11/12" />
      <SkeletonLine className="h-3.5 w-4/5" />
      <SkeletonLine className="mt-6 h-4 w-36" />
      <SkeletonLine className="h-16 w-full" />
    </div>
  ) : (
    <div className="space-y-6">
      <Section title="Summary">
        {analysis?.executive_summary ? (
          <p className="max-w-prose text-[16px] leading-[1.7] text-ink" lang={hasBangla(analysis.executive_summary) ? "bn" : undefined}>
            {analysis.executive_summary}
          </p>
        ) : (
          <div className="space-y-3">
            {doc.title_bn && (
              <p lang="bn" className="max-w-prose text-[16px] text-ink">
                {doc.title_bn}
              </p>
            )}
            <div className="flex flex-wrap items-center gap-3">
              <StatusBadge status="AWAITING_REVIEW" size="sm" />
              <span className="text-[14px] text-ink-2">No analysis has been run on this circular yet.</span>
              {isAdmin && (
                <button type="button" onClick={runAnalysis} disabled={analyzing} className="btn-secondary py-1">
                  <Sparkles className="h-3.5 w-3.5" />
                  {analyzing ? "Running..." : "Run analysis"}
                </button>
              )}
            </div>
          </div>
        )}
        {analysis?.purpose && (
          <p className="mt-3 max-w-prose text-[14.5px] leading-relaxed text-ink-2">
            <span className="font-semibold text-ink">Purpose. </span>
            {analysis.purpose}
          </p>
        )}
      </Section>

      <Section title="What has changed">
        {changes.length > 0 ? (
          <ul className="max-w-prose space-y-2.5">
            {changes.map((c, i) => (
              <li key={i} className="grid grid-cols-[1rem_1fr] gap-2 text-[15px] leading-relaxed text-ink">
                <span aria-hidden className="mt-[0.7em] h-1.5 w-1.5 rounded-full bg-accent" />
                <span>{c}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[14.5px] text-ink-3">
            {analysis ? "No changes to earlier circulars are listed. The requirements below are what this circular asks for." : "Shown once the circular is analysed."}
          </p>
        )}
      </Section>

      <Section title="Requirements" count={obligations.length}>
        {obligations.length === 0 ? (
          <div className="flex flex-wrap items-center gap-3 text-[14.5px] text-ink-3">
            <span>No requirements have been extracted for this circular yet.</span>
            {!analysis && isAdmin && (
              <button type="button" onClick={runAnalysis} disabled={analyzing} className="btn-secondary py-1">
                {analyzing ? "Extracting..." : "Extract requirements"}
              </button>
            )}
          </div>
        ) : (
          <ol className="divide-y divide-line">
            {obligations.map((obl, i) => {
              const citedPage = pages.find((p) => p.id === obl.page_id)?.page_number;
              return (
                <motion.li
                  key={obl.id}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.25, delay: Math.min(i, 8) * 0.03, ease: EASE_OUT }}
                  className="space-y-2.5 py-4 first:pt-0 last:pb-0"
                >
                  <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1.5">
                    <h4 className="max-w-prose text-[15.5px] font-semibold leading-snug text-ink">{obl.title}</h4>
                    {obl.obligation_type && <Tag tone="accent">{readable(obl.obligation_type)}</Tag>}
                  </div>
                  <p className="max-w-prose text-[15px] leading-relaxed text-ink-2">{obl.requirement_description}</p>
                  {obl.supporting_text && (
                    <blockquote className="quote max-w-prose" lang={hasBangla(obl.supporting_text) ? "bn" : undefined}>
                      &ldquo;{obl.supporting_text}&rdquo;
                    </blockquote>
                  )}
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[13px] text-ink-3">
                    <PageLink page={citedPage} onClick={() => citedPage && openPage(citedPage, obl.supporting_text, obl.quote_boxes)} />
                    <span>Applies to: {obl.applicability_summary || "Not stated"}</span>
                    {obl.explicit_deadline && <span className="font-semibold text-warn">Deadline: {obl.explicit_deadline}</span>}
                  </div>
                </motion.li>
              );
            })}
          </ol>
        )}
      </Section>

      <Section title="Who it applies to">
        {appliesTo.length > 0 ? (
          <ul className="max-w-prose space-y-1.5 text-[15px] text-ink">
            {appliesTo.map((t: string) => (
              <li key={t} className="grid grid-cols-[1rem_1fr] gap-2">
                <span aria-hidden className="mt-[0.65em] h-1.5 w-1.5 rounded-full bg-ink-3" />
                <span>{t}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[14.5px] text-ink-3">Not identified yet. Read the circular text for who it applies to.</p>
        )}
        {conditional && <p className="mt-2 max-w-prose text-[14.5px] text-ink-2">Scope: {conditional}</p>}
      </Section>

      <Section title="Dates">
        <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-3">
          <div>
            <dt className="text-[13px] text-ink-3">Issued</dt>
            <dd className="mt-0.5 text-[15px] font-semibold text-ink tabular-nums">{formatDate(doc.publication_date) || "Not stated"}</dd>
          </div>
          <div>
            <dt className="text-[13px] text-ink-3">Takes effect</dt>
            <dd className="mt-0.5 text-[15px] font-semibold text-ink tabular-nums">{formatDate(effective) || "Not stated"}</dd>
          </div>
          <div>
            <dt className="text-[13px] text-ink-3">Compliance deadline</dt>
            <dd className={`mt-0.5 text-[15px] font-semibold tabular-nums ${complianceDeadline ? "text-warn" : "text-ink"}`}>
              {complianceDeadline || "Not stated"}
            </dd>
          </div>
        </dl>
      </Section>

      <Section title="Exceptions and conditions">
        {Array.isArray(exemptions) && exemptions.length > 0 ? (
          <ul className="max-w-prose list-disc space-y-1 pl-5 text-[15px] text-ink marker:text-ink-3">
            {exemptions.map((ex: unknown, i: number) => (
              <li key={i}>{typeof ex === "string" ? ex : JSON.stringify(ex)}</li>
            ))}
          </ul>
        ) : conditional ? (
          <p className="max-w-prose text-[15px] text-ink">{conditional}</p>
        ) : (
          <p className="text-[14.5px] text-ink-3">No exceptions or special conditions identified yet.</p>
        )}
      </Section>

      {relationships.length > 0 && (
        <Section title="Related circulars" count={relationships.length}>
          <ul className="divide-y divide-line">
            {relationships.map((rel, idx) => {
              const relPage = rel.quote_boxes?.[0]?.page_number;
              return (
                <li key={rel.id ?? idx} className="space-y-1.5 py-3 first:pt-0 last:pb-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="refno">{rel.target_reference_hint || "Cited circular"}</span>
                    <Tag tone="info">{readable(rel.relationship_type)}</Tag>
                  </div>
                  {rel.supporting_quote && <blockquote className="quote max-w-prose">&ldquo;{rel.supporting_quote}&rdquo;</blockquote>}
                  {relPage && pages.length > 0 && (
                    <PageLink page={relPage} onClick={() => openPage(relPage, rel.supporting_quote, rel.quote_boxes)} />
                  )}
                </li>
              );
            })}
          </ul>
        </Section>
      )}

      <Section title="Ask this circular">
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
      </Section>
    </div>
  );

  return (
    <article className="rounded-panel border border-line bg-surface shadow-panel">
      {/* Document header */}
      <header className="space-y-3 px-5 pb-5 pt-5 sm:px-7 sm:pt-6">
        <div className="flex flex-wrap items-center gap-2">
          <span className="refno">{doc.reference_number || "Circular"}</span>
          <StatusBadge status={doc.publication_status} />
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
          {pageCount > 0 && <span className="tabular-nums">{pageCount} pages</span>}
          <span>Bangladesh Bank</span>
        </div>
        <div className="flex flex-wrap items-center gap-2 pt-1">
          {pdfButton}
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

        {isAdmin && (
          <div className="mt-2 space-y-2 rounded-panel bg-sunken px-3 py-2.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="mr-1 flex items-center gap-1.5 text-[13px] font-semibold text-ink-2">
                <ShieldCheck className="h-4 w-4" strokeWidth={1.75} />
                Admin
              </span>
              <button type="button" onClick={runAnalysis} disabled={analyzing} className="btn-secondary py-1">
                <RefreshCw className={`h-3.5 w-3.5 ${analyzing ? "animate-spin" : ""}`} />
                {analyzing ? "Analysing..." : "Run analysis"}
              </button>
              <button type="button" onClick={signOff} disabled={publishing} className="btn-secondary py-1">
                {publishing ? "Signing off..." : "Approve and sign off"}
              </button>
              <button type="button" onClick={reextract} disabled={reextracting} className="btn-secondary py-1">
                {reextracting ? "Re-extracting..." : "Re-extract pages"}
              </button>
              <Link href="/admin" className="btn-ghost py-1">
                Console
              </Link>
            </div>
            {adminMessage && <Notice kind={adminMessage.type === "error" ? "error" : "success"}>{adminMessage.text}</Notice>}
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
                versionId={doc.current_version_id || doc.versions?.[0]?.id}
                pages={pages}
                pageNumber={pageNumber}
                onPageChange={(n) => {
                  setPageNumber(n);
                  setHighlight(null);
                }}
                onClose={() => setPagePanelOpen(false)}
                highlight={highlight}
              />
            </div>
          </motion.div>
        )}
      </div>
    </article>
  );
}
