"use client";

import { useState } from "react";
import Link from "next/link";
import { BookOpenText, ExternalLink, X } from "lucide-react";
import { InForceBadge } from "../StatusBadge";
import PagePanel from "../PagePanel";
import { hasBangla } from "../ui";
import { fetchDocumentPages, type DocumentPage } from "@/services/api";
import type { ItemRead } from "@/services/workspaceApi";
import { formatDate } from "@/services/workspaceRules";

/** The exact quote, its circular and page, and a way to see the marked page. */
export default function SourceQuote({ item }: { item: ItemRead }) {
  const s = item.source;
  const [open, setOpen] = useState(false);
  const [pages, setPages] = useState<DocumentPage[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pageNo, setPageNo] = useState(s.page_number ?? 1);

  const show = async () => {
    setOpen(true);
    setPageNo(s.page_number ?? 1);
    if (pages || !s.document_id || !s.version_id) return;
    try {
      setPages(await fetchDocumentPages(s.document_id, s.version_id));
    } catch (e: any) {
      setError(e?.message || "Could not load the page.");
    }
  };


  return (
    <section className="space-y-3" aria-label="Source" data-testid="source-quote">
      {s.quote && (
        <blockquote className="quote" lang={hasBangla(s.quote) ? "bn" : undefined}>
          &ldquo;{s.quote}&rdquo;
        </blockquote>
      )}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[13.5px] text-ink-2">
        <span className="font-semibold tabular-nums text-accent">
          {s.reference_number || "Circular"}
          {s.page_number ? `, page ${s.page_number}` : ""}
        </span>
        <InForceBadge info={{ status: s.in_force_status, byId: s.in_force_by?.id, byRef: s.in_force_by?.reference_number }} size="sm" />
      </div>
      {s.title && <p className="text-[14px] text-ink-2">{s.title}</p>}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-ink-3">
        {s.publication_date && <span>Published {formatDate(s.publication_date)}</span>}
      </div>
      <div className="flex flex-wrap gap-2">
        {s.version_id && s.document_id && (
          <button type="button" className="btn-secondary min-h-[44px] sm:min-h-0" onClick={show}>
            <BookOpenText className="h-4 w-4" strokeWidth={1.75} />
            View on page {s.page_number ?? 1}
          </button>
        )}
        {s.page_link && (
          <Link href={s.page_link} className="btn-secondary min-h-[44px] sm:min-h-0">
            <ExternalLink className="h-4 w-4" strokeWidth={1.75} />
            Open circular
          </Link>
        )}
      </div>

      {open && (
        <div className="fixed inset-0 z-[70] flex flex-col bg-canvas lg:static lg:z-auto lg:block lg:bg-transparent" role="dialog" aria-label="Source page">
          <div className="flex items-center justify-between border-b border-line px-4 py-2 lg:hidden">
            <span className="text-[14px] font-semibold text-ink">Source page</span>
            <button type="button" className="btn-ghost h-11 w-11 p-0" onClick={() => setOpen(false)} aria-label="Close the page">
              <X className="h-5 w-5" />
            </button>
          </div>
          <div className="min-h-0 flex-1 overflow-auto p-2 lg:overflow-visible lg:p-0">
            {error ? (
              <p className="p-3 text-[14px] text-bad">{error}</p>
            ) : !pages ? (
              <p className="p-3 text-[14px] text-ink-3">Loading the page…</p>
            ) : (
              <PagePanel
                documentId={s.document_id!}
                versionId={s.version_id!}
                pages={pages}
                pageNumber={pageNo}
                onPageChange={setPageNo}
                onClose={() => setOpen(false)}
                highlight={s.quote ? { text: s.quote, boxes: s.quote_boxes ?? null, key: item.id } : null}
                canEdit={false}
              />
            )}
          </div>
        </div>
      )}
    </section>
  );
}
