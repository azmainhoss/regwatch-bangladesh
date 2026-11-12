"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { AlignLeft, ChevronLeft, ChevronRight, FileImage, PenLine, X, ZoomIn, ZoomOut } from "lucide-react";
import { fetchPageImage, type Box2D, type DocumentPage, type QuoteBox } from "@/services/api";
import StatusBadge, { Tag } from "./StatusBadge";
import { EASE_OUT, hasBangla } from "./ui";

/** A quote to show on the source page: its text, and its boxes on the page when known. */
export interface PageHighlight {
  text: string;
  boxes?: QuoteBox[] | null;
  /** Changes on every click, so clicking the same quote again scrolls back to it. */
  key: string;
}

interface Props {
  documentId: string;
  versionId?: string;
  pages: DocumentPage[];
  pageNumber: number;
  onPageChange: (n: number) => void;
  onClose: () => void;
  highlight?: PageHighlight | null;
}

type View = "image" | "text";

const ZOOMS = [1, 1.5, 2] as const;

function normalise(s: string) {
  return s.replace(/\s+/g, " ").trim();
}

/** A regex that lets any run of whitespace in the quote match any run in the page. */
function quotePattern(quote: string): RegExp | null {
  const q = normalise(quote);
  if (q.length < 8) return null;
  const pattern = q
    .split(" ")
    .map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .join("\\s+");
  try {
    return new RegExp(pattern);
  } catch {
    return null;
  }
}

/** Splits text around the first exact (whitespace-insensitive) match of the quote. */
function markQuote(text: string, quote?: string | null): React.ReactNode {
  if (!quote) return text;
  const re = quotePattern(quote);
  const match = re?.exec(text);
  if (!match) return text;
  return (
    <>
      {text.slice(0, match.index)}
      <mark className="rounded-[3px] bg-[rgb(var(--highlight))] px-0.5 text-ink [box-decoration-break:clone]">{match[0]}</mark>
      {text.slice(match.index + match[0].length)}
    </>
  );
}

function union(boxes: Box2D[]): Box2D {
  return [
    Math.min(...boxes.map((b) => b[0])),
    Math.min(...boxes.map((b) => b[1])),
    Math.max(...boxes.map((b) => b[2])),
    Math.max(...boxes.map((b) => b[3])),
  ];
}

/**
 * Finds a quote in the page's own line boxes when the quote came without boxes (answers to
 * questions, older analyses). Lines with word boxes are trimmed to the quoted words.
 */
function boxesFromLines(page: DocumentPage, quote: string): Box2D[] {
  const lines = page.line_boxes;
  if (!lines?.length || !quote) return [];
  let joined = "";
  const spans: Array<{ start: number; end: number; box: Box2D; words: Array<{ start: number; end: number; box: Box2D }> }> = [];
  for (const line of lines) {
    const text = (line?.text ?? "").trim();
    if (!text || !Array.isArray(line.box_2d)) continue;
    const start = joined.length;
    const words: Array<{ start: number; end: number; box: Box2D }> = [];
    let cursor = 0;
    for (const w of line.words ?? []) {
      const wt = (w?.text ?? "").trim();
      if (!wt || !Array.isArray(w.box_2d)) continue;
      const pos = text.indexOf(wt, cursor);
      if (pos === -1) continue;
      cursor = pos + wt.length;
      words.push({ start: start + pos, end: start + cursor, box: w.box_2d });
    }
    spans.push({ start, end: start + text.length, box: line.box_2d, words });
    joined += text + "\n";
  }
  const out: Box2D[] = [];
  // Quotes made of several passages are joined with " … ".
  for (const part of quote.split(" … ")) {
    const match = quotePattern(part)?.exec(joined);
    if (!match) continue;
    const s = match.index;
    const e = s + match[0].length;
    for (const span of spans) {
      if (span.start >= e || span.end <= s) continue;
      const hit = span.words.filter((w) => w.start < e && w.end > s).map((w) => w.box);
      out.push(hit.length ? union(hit) : span.box);
    }
  }
  return out;
}

// Page images already fetched, as object URLs. Kept small; the oldest is released first.
const imageCache = new Map<string, Promise<string>>();
const IMAGE_CACHE_LIMIT = 24;

function loadImage(documentId: string, versionId: string, pageNo: number, dpi: number): Promise<string> {
  const key = `${documentId}:${versionId}:${pageNo}:${dpi}`;
  const hit = imageCache.get(key);
  if (hit) {
    imageCache.delete(key);
    imageCache.set(key, hit);
    return hit;
  }
  const p = fetchPageImage(documentId, versionId, pageNo, dpi);
  p.catch(() => imageCache.delete(key));
  imageCache.set(key, p);
  while (imageCache.size > IMAGE_CACHE_LIMIT) {
    const oldest = imageCache.keys().next().value as string;
    imageCache.get(oldest)?.then((url) => URL.revokeObjectURL(url)).catch(() => undefined);
    imageCache.delete(oldest);
  }
  return p;
}

function usePageImage(documentId: string, versionId: string | undefined, pageNo: number | undefined, dpi: number) {
  const [state, setState] = useState<{ key: string; src: string | null; failed: boolean }>({ key: "", src: null, failed: false });
  const pageKey = `${documentId}:${versionId}:${pageNo}`;
  useEffect(() => {
    if (!versionId || !pageNo) return;
    let live = true;
    loadImage(documentId, versionId, pageNo, dpi)
      .then((src) => live && setState({ key: pageKey, src, failed: false }))
      .catch(() => live && setState((prev) => (prev.key === pageKey && prev.src ? prev : { key: pageKey, src: null, failed: true })));
    return () => {
      live = false;
    };
  }, [documentId, versionId, pageNo, dpi, pageKey]);
  // An image of another page never shows here, even for a moment.
  const current = state.key === pageKey;
  return { src: current ? state.src : null, failed: current && state.failed, loading: !current || (!state.src && !state.failed) };
}

function ToolbarButton({
  active,
  onClick,
  label,
  disabled,
  children,
}: {
  active?: boolean;
  onClick: () => void;
  label: string;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      aria-pressed={active}
      title={label}
      className={`inline-flex h-7 items-center gap-1 rounded-[5px] px-2 text-[12.5px] font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
        active ? "bg-surface text-ink shadow-[0_1px_2px_rgb(var(--shadow)/0.12)]" : "text-ink-3 hover:text-ink"
      }`}
    >
      {children}
    </button>
  );
}

/**
 * The source page beside the analysis: the original page image with the quoted lines
 * marked, or the extracted text. The text view is used when the image cannot be loaded
 * or when a quote has no position on the page.
 */
export default function PagePanel({ documentId, versionId, pages, pageNumber, onPageChange, onClose, highlight }: Props) {
  const reduceMotion = useReducedMotion();
  const sorted = useMemo(() => [...pages].sort((a, b) => a.page_number - b.page_number), [pages]);
  const page = sorted.find((p) => p.page_number === pageNumber) ?? sorted[0];
  const idx = page ? sorted.indexOf(page) : -1;
  const text = page?.raw_text?.trim() ?? "";
  const quote = highlight?.text ?? null;
  const body = useMemo(() => markQuote(text, quote), [text, quote]);

  const [zoom, setZoom] = useState<(typeof ZOOMS)[number]>(1);
  const [chosenView, setChosenView] = useState<View | null>(null);
  const image = usePageImage(documentId, versionId, page?.page_number, zoom > 1 ? 192 : 144);

  // Boxes for this page: the quote's own boxes, or found in the page's line boxes.
  const boxes = useMemo<Box2D[]>(() => {
    if (!page || !highlight) return [];
    const own = (highlight.boxes ?? []).filter((b) => b.page_number === page.page_number && Array.isArray(b.box_2d)).map((b) => b.box_2d);
    if (own.length) return own;
    return boxesFromLines(page, highlight.text);
  }, [page, highlight]);

  // A new quote or page goes back to the automatic choice of view.
  useEffect(() => setChosenView(null), [highlight?.key, page?.page_number]);

  const canShowImage = !!versionId && !image.failed;
  const autoView: View = !canShowImage ? "text" : highlight && boxes.length === 0 && text ? "text" : "image";
  const view: View = chosenView === "image" && !canShowImage ? "text" : chosenView ?? autoView;

  const scrollRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const [imgReady, setImgReady] = useState(false);
  useEffect(() => setImgReady(false), [image.src]);

  // Bring the first marked line into view once the image has its size.
  const scrollToFirst = useCallback(() => {
    const box = scrollRef.current;
    const img = imgRef.current;
    if (!box || !img || boxes.length === 0) return;
    const first = boxes.reduce((a, b) => (b[0] < a[0] ? b : a));
    const imgRect = img.getBoundingClientRect();
    const boxRect = box.getBoundingClientRect();
    const top = imgRect.top - boxRect.top + box.scrollTop + (first[0] / 1000) * imgRect.height;
    const left = imgRect.left - boxRect.left + box.scrollLeft + (first[1] / 1000) * imgRect.width;
    box.scrollTo({
      top: Math.max(0, top - box.clientHeight * 0.3),
      left: zoom > 1 ? Math.max(0, left - 24) : 0,
      behavior: reduceMotion ? "auto" : "smooth",
    });
  }, [boxes, zoom, reduceMotion]);

  useLayoutEffect(() => {
    if (view === "image" && imgReady) scrollToFirst();
  }, [view, imgReady, highlight?.key, scrollToFirst]);

  // In the text view, scroll the marked passage into view.
  useEffect(() => {
    if (view !== "text" || !quote) return;
    const mark = scrollRef.current?.querySelector("mark");
    mark?.scrollIntoView({ block: "center", behavior: reduceMotion ? "auto" : "smooth" });
  }, [view, quote, highlight?.key, page?.page_number, reduceMotion]);

  const quoteNotOnImage = !!highlight && view === "image" && boxes.length === 0;

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

      {page && (
        <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-1.5">
          <div role="group" aria-label="Show the page as" className="inline-flex rounded-control bg-sunken p-0.5">
            <ToolbarButton active={view === "image"} onClick={() => setChosenView("image")} label="Original page" disabled={!canShowImage}>
              <FileImage className="h-3.5 w-3.5" strokeWidth={1.75} />
              Page
            </ToolbarButton>
            <ToolbarButton active={view === "text"} onClick={() => setChosenView("text")} label="Extracted text">
              <AlignLeft className="h-3.5 w-3.5" strokeWidth={1.75} />
              Text
            </ToolbarButton>
          </div>
          {view === "image" && (
            <div role="group" aria-label="Zoom" className="inline-flex items-center rounded-control bg-sunken p-0.5">
              <ToolbarButton onClick={() => setZoom(ZOOMS[Math.max(0, ZOOMS.indexOf(zoom) - 1)])} label="Zoom out" disabled={zoom === ZOOMS[0]}>
                <ZoomOut className="h-3.5 w-3.5" strokeWidth={1.75} />
              </ToolbarButton>
              <ToolbarButton onClick={() => setZoom(1)} label="Fit to width" active={zoom === 1}>
                <span className="min-w-[2.6rem] tabular-nums">{zoom === 1 ? "Fit" : `${Math.round(zoom * 100)}%`}</span>
              </ToolbarButton>
              <ToolbarButton
                onClick={() => setZoom(ZOOMS[Math.min(ZOOMS.length - 1, ZOOMS.indexOf(zoom) + 1)])}
                label="Zoom in"
                disabled={zoom === ZOOMS[ZOOMS.length - 1]}
              >
                <ZoomIn className="h-3.5 w-3.5" strokeWidth={1.75} />
              </ToolbarButton>
            </div>
          )}
          {highlight && view === "image" && boxes.length > 0 && (
            <span className="ml-auto hidden items-center gap-1.5 text-[12.5px] text-ink-3 sm:flex">
              <span aria-hidden className="h-2.5 w-3.5 rounded-[2px] bg-marker/60 ring-1 ring-inset ring-marker-edge/50" />
              Quote marked
            </span>
          )}
        </div>
      )}

      {page && (image.failed || quoteNotOnImage) && (
        <p role="status" className="border-b border-line bg-sunken/60 px-4 py-1.5 text-[12.5px] text-ink-3">
          {image.failed
            ? "The page image could not be loaded, so the extracted text is shown."
            : "This quote has no position on the page image. Switch to Text to see it marked."}
        </p>
      )}

      <div ref={scrollRef} className="relative min-h-0 flex-1 overflow-auto overscroll-contain">
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={`${page?.id ?? "empty"}:${view}`}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className={view === "image" && page ? "p-3" : "px-5 py-4"}
          >
            {!page ? (
              <p className="text-[14px] text-ink-3">No extracted pages for this circular yet.</p>
            ) : view === "image" ? (
              <div style={{ width: `${zoom * 100}%` }} className="mx-auto">
                {image.src ? (
                  <figure className="relative isolate overflow-hidden rounded-[4px] bg-white ring-1 ring-line">
                    {/* eslint-disable-next-line @next/next/no-img-element -- an object URL of a rendered page, not a static asset */}
                    <img
                      ref={imgRef}
                      src={image.src}
                      alt={`Page ${page.page_number} of the original circular`}
                      onLoad={() => setImgReady(true)}
                      className="block h-auto w-full select-none dark:brightness-[0.92]"
                      draggable={false}
                    />
                    <div aria-hidden className="pointer-events-none absolute inset-0">
                      <AnimatePresence>
                        {boxes.map((b, i) => (
                          <motion.span
                            key={`${highlight?.key}:${i}`}
                            initial={{ opacity: 0, scaleX: 0.96 }}
                            animate={{ opacity: 1, scaleX: 1 }}
                            exit={{ opacity: 0 }}
                            transition={{ duration: reduceMotion ? 0 : 0.35, delay: reduceMotion ? 0 : Math.min(i, 10) * 0.035, ease: EASE_OUT }}
                            className="absolute origin-left rounded-[2px] bg-marker/45 mix-blend-multiply ring-1 ring-inset ring-marker-edge/40"
                            style={{
                              top: `${(b[0] - 3) / 10}%`,
                              left: `${(b[1] - 4) / 10}%`,
                              height: `${(b[2] - b[0] + 6) / 10}%`,
                              width: `${(b[3] - b[1] + 8) / 10}%`,
                            }}
                          />
                        ))}
                      </AnimatePresence>
                    </div>
                    {highlight && boxes.length > 0 && <figcaption className="sr-only">Quoted passage marked: {highlight.text}</figcaption>}
                  </figure>
                ) : (
                  <div className="aspect-[1/1.414] w-full animate-pulse rounded-[4px] bg-sunken ring-1 ring-line" aria-busy="true" aria-label="Loading page image" />
                )}
              </div>
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
