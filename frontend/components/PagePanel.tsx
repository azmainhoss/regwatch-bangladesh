"use client";

import { useMemo } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronLeft, ChevronRight, PenLine, X } from "lucide-react";
import type { DocumentPage } from "@/services/api";
import StatusBadge, { Tag } from "./StatusBadge";
import { EASE_OUT, hasBangla } from "./ui";

interface Props {
  pages: DocumentPage[];
  pageNumber: number;
  onPageChange: (n: number) => void;
  onClose: () => void;
  /** A quote to mark in the page text when it appears there word for word. */
  highlight?: string | null;
}

function normalise(s: string) {
  return s.replace(/\s+/g, " ").trim();
}

/** Splits text around the first exact (whitespace-insensitive) match of the quote. */
function markQuote(text: string, quote?: string | null): React.ReactNode {
  if (!quote) return text;
  const q = normalise(quote);
  if (q.length < 8) return text;
  // Build a regex that lets any run of whitespace in the quote match any run in the page.
  const pattern = q
    .split(" ")
    .map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .join("\\s+");
  let match: RegExpExecArray | null = null;
  try {
    match = new RegExp(pattern).exec(text);
  } catch {
    return text;
  }
  if (!match) return text;
  return (
    <>
      {text.slice(0, match.index)}
      <mark className="rounded-[3px] bg-[rgb(var(--highlight))] px-0.5 text-ink [box-decoration-break:clone]">{match[0]}</mark>
      {text.slice(match.index + match[0].length)}
    </>
  );
}

/**
 * The source page beside the analysis. It shows the extracted text today; the same
 * panel is sized for a portrait page so the original page image can sit here later,
 * with quoted lines drawn over it.
 */
export default function PagePanel({ pages, pageNumber, onPageChange, onClose, highlight }: Props) {
  const sorted = useMemo(() => [...pages].sort((a, b) => a.page_number - b.page_number), [pages]);
  const page = sorted.find((p) => p.page_number === pageNumber) ?? sorted[0];
  const idx = page ? sorted.indexOf(page) : -1;
  const text = page?.raw_text?.trim() ?? "";
  const body = useMemo(() => markQuote(text, highlight), [text, highlight]);

  return (
    <section aria-label="Source page" className="flex h-full min-h-0 flex-col rounded-panel border border-line bg-surface">
      <header className="flex items-center gap-2 border-b border-line px-3 py-2">
        <button
          type="button"
          onClick={() => idx > 0 && onPageChange(sorted[idx - 1].page_number)}
          disabled={idx <= 0}
          aria-label="Previous page"
          className="btn-ghost h-8 w-8 p-0"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
        <p className="text-[14px] font-semibold text-ink tabular-nums">
          {page ? `Page ${page.page_number}` : "No pages"}
          {sorted.length > 0 && <span className="font-normal text-ink-3"> of {sorted.length}</span>}
        </p>
        <button
          type="button"
          onClick={() => idx >= 0 && idx < sorted.length - 1 && onPageChange(sorted[idx + 1].page_number)}
          disabled={idx < 0 || idx >= sorted.length - 1}
          aria-label="Next page"
          className="btn-ghost h-8 w-8 p-0"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
        <div className="ml-auto flex items-center gap-1.5">
          {page?.quality_status && !page.quality_status.startsWith("SUCCESS") && <StatusBadge status={page.quality_status} size="sm" />}
          {page?.is_human_corrected && (
            <Tag tone="ok" title="A person corrected this page's text">
              <PenLine className="h-3 w-3" /> Corrected
            </Tag>
          )}
          <button type="button" onClick={onClose} aria-label="Close source page" className="btn-ghost h-8 w-8 p-0">
            <X className="h-4 w-4" />
          </button>
        </div>
      </header>

      {sorted.length > 1 && (
        <nav aria-label="Pages" className="flex gap-1 overflow-x-auto border-b border-line px-3 py-2">
          {sorted.map((p) => {
            const active = p.page_number === page?.page_number;
            return (
              <button
                key={p.id}
                type="button"
                onClick={() => onPageChange(p.page_number)}
                aria-current={active ? "page" : undefined}
                className={`relative min-w-[2rem] rounded-control px-2 py-1 text-[13px] font-semibold tabular-nums transition-colors ${
                  active ? "text-accent-ink" : "text-ink-2 hover:bg-sunken"
                }`}
              >
                {active && (
                  <motion.span layoutId="page-chip" className="absolute inset-0 rounded-control bg-accent" transition={{ duration: 0.2, ease: EASE_OUT }} />
                )}
                <span className="relative">{p.page_number}</span>
              </button>
            );
          })}
        </nav>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto">
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={page?.id ?? "empty"}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="px-5 py-4"
          >
            {!page ? (
              <p className="text-[14px] text-ink-3">No extracted pages for this circular yet.</p>
            ) : text ? (
              <div
                lang={hasBangla(text) ? "bn" : undefined}
                className="max-w-prose whitespace-pre-wrap break-words text-[14.5px] leading-[1.75] text-ink"
              >
                {body}
              </div>
            ) : (
              <div className="space-y-2 text-[14px] text-ink-3">
                <p>This page has no text yet.</p>
                {page.quality_status === "PENDING_VISION" && (
                  <p>It has no usable text layer, so it is waiting to be read from the page image.</p>
                )}
                {page.quality_status === "NEEDS_HUMAN_REVIEW" && <p>Reading it automatically did not work. A person needs to check it.</p>}
                {page.vision_error && <p className="text-bad">Last attempt: {page.vision_error}</p>}
              </div>
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </section>
  );
}
