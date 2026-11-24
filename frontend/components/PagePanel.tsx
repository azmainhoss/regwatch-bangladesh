"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { AlignLeft, ChevronLeft, ChevronRight, Crosshair, FileImage, Maximize2, Minimize2, PenLine, Pencil, X, ZoomIn, ZoomOut } from "lucide-react";
import { submitPageCorrection, type Box2D, type DocumentPage, type QuoteBox } from "@/services/api";
import { loadPageImage, peekPageImage } from "@/services/pageImages";
import StatusBadge, { Tag } from "./StatusBadge";
import { EASE_OUT, Notice, hasBangla } from "./ui";

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
  /** True for administrators: shows the "Edit text" button. */
  canEdit?: boolean;
  /** Called with the saved page so every screen showing it redraws at once. */
  onPageSaved?: (page: DocumentPage) => void;
  /** A number that goes up each time a screen asks for the text editor to open on this page. */
  editRequest?: number;
  /** Inside the circular's side panel, which has its own frame and close button. */
  bare?: boolean;
}

/** The text a reader sees: a person's correction when there is one, else the extracted text. */
export function pageText(page?: DocumentPage | null): string {
  if (!page) return "";
  const corrected = page.is_human_corrected ? page.human_corrected_text ?? page.cleaned_text : null;
  return (corrected ?? page.raw_text ?? "").trim();
}

function correctionDate(value: string) {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

type View = "image" | "text";

const MIN_ZOOM = 1;
const MAX_ZOOM = 4;
const clampZoom = (z: number) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Math.round(z * 100) / 100));

/**
 * The zoom that makes a marked quote readable: wide enough that the page text is a comfortable size
 * (about 1000 px of page width), but never so far that the quote no longer fits across the panel
 * on a wide screen. On a phone the text size wins, and the panel scrolls sideways to the quote.
 */
function readingZoom(containerWidth: number, boxes: Box2D[]): number {
  if (!containerWidth) return 1;
  const left = Math.min(...boxes.map((b) => b[1]));
  const right = Math.max(...boxes.map((b) => b[3]));
  const quoteWidth = Math.max(0.15, (right - left) / 1000 + 0.04);
  const fitQuote = 1 / quoteWidth;
  const readable = Math.min(2.2, 1000 / containerWidth);
  return clampZoom(Math.max(fitQuote > 1.05 ? Math.min(fitQuote, 2.5) : 1, readable));
}

/** Joins the line breaks that only come from the PDF's line wrapping, so the text reads as paragraphs. */
function reflow(text: string): string {
  return text.replace(/([^\n.:;!?।)\]|])\n(?!\s*\n)(?=\s*(?![([]?[a-zA-Z0-9]{1,3}[.)\]]\s)(?![•\-–*]\s)\S)/g, "$1 ");
}

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

function usePageImage(documentId: string, versionId: string | undefined, pageNo: number | undefined, dpi: number) {
  const [state, setState] = useState<{ key: string; src: string | null; failed: boolean }>({ key: "", src: null, failed: false });
  const pageKey = `${documentId}:${versionId}:${pageNo}`;
  useEffect(() => {
    if (!versionId || !pageNo) return;
    let live = true;
    loadPageImage(documentId, versionId, pageNo, dpi)
      .then((src) => live && setState({ key: pageKey, src, failed: false }))
      .catch(() => live && setState((prev) => (prev.key === pageKey && prev.src ? prev : { key: pageKey, src: null, failed: true })));
    return () => {
      live = false;
    };
  }, [documentId, versionId, pageNo, dpi, pageKey]);
  // An image that was fetched ahead of time is drawn in the same frame; an image of another page never shows here.
  const cached = versionId && pageNo ? peekPageImage(documentId, versionId, pageNo, dpi) : null;
  const current = state.key === pageKey;
  if (!current && cached) return { src: cached, failed: false, loading: false };
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
export default function PagePanel({ documentId, versionId, pages, pageNumber, onPageChange, onClose, highlight, canEdit, onPageSaved, editRequest, bare }: Props) {
  const reduceMotion = useReducedMotion();
  const sorted = useMemo(() => [...pages].sort((a, b) => a.page_number - b.page_number), [pages]);
  const page = sorted.find((p) => p.page_number === pageNumber) ?? sorted[0];
  const idx = page ? sorted.indexOf(page) : -1;
  const text = pageText(page);
  const quote = highlight?.text ?? null;
  const body = useMemo(() => markQuote(reflow(text), quote), [text, quote]);

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const startEdit = () => {
    setDraft(text);
    setReason("");
    setSaveError(null);
    setEditing(true);
  };
  const cancelEdit = () => {
    if (saving) return;
    setEditing(false);
    setSaveError(null);
  };
  const seenEditRequest = useRef(editRequest ?? 0);
  useEffect(() => {
    if (!canEdit || !editRequest || editRequest === seenEditRequest.current) return;
    seenEditRequest.current = editRequest;
    startEdit();
    // startEdit only reads the page text at the moment of the request.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editRequest, canEdit]);
  const saveEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!page || !versionId || saving) return;
    if (!draft.trim()) return setSaveError("The page text cannot be empty.");
    if (!reason.trim()) return setSaveError("Please say why you are changing it.");
    setSaving(true);
    setSaveError(null);
    try {
      const res = await submitPageCorrection(documentId, versionId, page.page_number, draft, reason.trim());
      onPageSaved?.(res.page);
      setEditing(false);
    } catch (err: any) {
      setSaveError(err?.message || "Could not save the text.");
    } finally {
      setSaving(false);
    }
  };

  const [zoom, setZoomState] = useState(1);
  const [full, setFull] = useState(false);
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
  const view: View = editing ? "text" : chosenView === "image" && !canShowImage ? "text" : chosenView ?? autoView;

  const scrollRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const [imgReady, setImgReady] = useState(false);
  useEffect(() => setImgReady(false), [image.src]);

  // Zoom keeps the point under the cursor or fingers in place: the scroll position is corrected right after the redraw.
  const anchor = useRef<{ x: number; y: number; from: number } | null>(null);
  const setZoom = useCallback((next: number, at?: { x: number; y: number }) => {
    setZoomState((prev) => {
      const z = clampZoom(next);
      if (z === prev) return prev;
      const box = scrollRef.current;
      anchor.current = box ? { x: at?.x ?? box.clientWidth / 2, y: at?.y ?? box.clientHeight / 2, from: prev } : null;
      return z;
    });
  }, []);
  useLayoutEffect(() => {
    const box = scrollRef.current;
    const a = anchor.current;
    if (!box || !a) return;
    anchor.current = null;
    const k = zoom / a.from;
    box.scrollLeft = (box.scrollLeft + a.x) * k - a.x;
    box.scrollTop = (box.scrollTop + a.y) * k - a.y;
  }, [zoom]);

  // Bring the first marked line into view once the image has its size.
  const scrollToFirst = useCallback(() => {
    const box = scrollRef.current;
    const img = imgRef.current;
    if (!box || !img || boxes.length === 0) return;
    const first = boxes.reduce((a, b) => (b[0] < a[0] ? b : a));
    const leftMost = Math.min(...boxes.map((b) => b[1]));
    const imgRect = img.getBoundingClientRect();
    const boxRect = box.getBoundingClientRect();
    const top = imgRect.top - boxRect.top + box.scrollTop + (first[0] / 1000) * imgRect.height;
    const left = imgRect.left - boxRect.left + box.scrollLeft + (leftMost / 1000) * imgRect.width;
    box.scrollTo({
      top: Math.max(0, top - box.clientHeight * 0.25),
      left: zoom > 1 ? Math.max(0, left - 16) : 0,
      behavior: reduceMotion ? "auto" : "smooth",
    });
  }, [boxes, zoom, reduceMotion]);

  // A new quote: zoom in until it is readable, then scroll to it.
  const zoomedFor = useRef<string | null>(null);
  useLayoutEffect(() => {
    if (view !== "image" || !highlight || boxes.length === 0 || zoomedFor.current === highlight.key) return;
    zoomedFor.current = highlight.key;
    anchor.current = null;
    setZoomState(readingZoom(scrollRef.current?.clientWidth ?? 0, boxes));
  }, [view, highlight, boxes]);

  useLayoutEffect(() => {
    if (view === "image" && imgReady) scrollToFirst();
    // Zoom is left out on purpose: zooming by hand must not jump back to the quote.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, imgReady, highlight?.key, zoomedFor.current]);

  // In the text view, scroll the marked passage into view.
  useEffect(() => {
    if (view !== "text" || !quote) return;
    const mark = scrollRef.current?.querySelector("mark");
    mark?.scrollIntoView({ block: "center", behavior: reduceMotion ? "auto" : "smooth" });
  }, [view, quote, highlight?.key, page?.page_number, reduceMotion]);

  // Trackpad pinch and Ctrl + wheel zoom the page (not the whole browser window).
  useEffect(() => {
    const box = scrollRef.current;
    if (!box || view !== "image") return;
    const onWheel = (e: WheelEvent) => {
      if (!e.ctrlKey && !e.metaKey) return;
      e.preventDefault();
      const r = box.getBoundingClientRect();
      setZoomState((prev) => {
        const z = clampZoom(prev * Math.exp(-e.deltaY * 0.01));
        if (z !== prev) anchor.current = { x: e.clientX - r.left, y: e.clientY - r.top, from: prev };
        return z;
      });
    };
    box.addEventListener("wheel", onWheel, { passive: false });
    return () => box.removeEventListener("wheel", onWheel);
  }, [view]);

  // Two-finger pinch on a phone zooms the page; one finger scrolls it as usual.
  const pinch = useRef<{ dist: number; zoom: number } | null>(null);
  useEffect(() => {
    const box = scrollRef.current;
    if (!box || view !== "image") return;
    const dist = (t: TouchList) => Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY);
    const onStart = (e: TouchEvent) => {
      if (e.touches.length === 2) pinch.current = { dist: dist(e.touches), zoom: zoomRef.current };
    };
    const onMove = (e: TouchEvent) => {
      if (e.touches.length !== 2 || !pinch.current) return;
      e.preventDefault();
      const r = box.getBoundingClientRect();
      const cx = (e.touches[0].clientX + e.touches[1].clientX) / 2 - r.left;
      const cy = (e.touches[0].clientY + e.touches[1].clientY) / 2 - r.top;
      const target = clampZoom(pinch.current.zoom * (dist(e.touches) / pinch.current.dist));
      setZoomState((prev) => {
        if (target !== prev) anchor.current = { x: cx, y: cy, from: prev };
        return target;
      });
    };
    const onEnd = (e: TouchEvent) => {
      if (e.touches.length < 2) pinch.current = null;
    };
    box.addEventListener("touchstart", onStart, { passive: true });
    box.addEventListener("touchmove", onMove, { passive: false });
    box.addEventListener("touchend", onEnd);
    return () => {
      box.removeEventListener("touchstart", onStart);
      box.removeEventListener("touchmove", onMove);
      box.removeEventListener("touchend", onEnd);
    };
  }, [view]);
  const zoomRef = useRef(zoom);
  zoomRef.current = zoom;

  // With a mouse: drag to move around a zoomed page, double-click to zoom in or back out.
  const drag = useRef<{ x: number; y: number; left: number; top: number } | null>(null);
  const [dragging, setDragging] = useState(false);
  const onMouseDown = (e: React.MouseEvent) => {
    if (zoom <= 1 || e.button !== 0 || !scrollRef.current) return;
    drag.current = { x: e.clientX, y: e.clientY, left: scrollRef.current.scrollLeft, top: scrollRef.current.scrollTop };
    setDragging(true);
    e.preventDefault();
  };
  useEffect(() => {
    if (!dragging) return;
    const move = (e: MouseEvent) => {
      const d = drag.current;
      const box = scrollRef.current;
      if (!d || !box) return;
      box.scrollLeft = d.left - (e.clientX - d.x);
      box.scrollTop = d.top - (e.clientY - d.y);
    };
    const up = () => {
      drag.current = null;
      setDragging(false);
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    return () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
  }, [dragging]);
  const onDoubleClick = (e: React.MouseEvent) => {
    const r = scrollRef.current?.getBoundingClientRect();
    if (!r) return;
    setZoom(zoom > 1.2 ? 1 : 2, { x: e.clientX - r.left, y: e.clientY - r.top });
  };

  // Full screen: Escape goes back to the side panel.
  useEffect(() => {
    if (!full) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setFull(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [full]);

  const quoteNotOnImage = !!highlight && view === "image" && boxes.length === 0;

  // Left and right arrow keys turn the page (not while typing or editing).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (editing || e.altKey || e.ctrlKey || e.metaKey) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName))) return;
      if (e.key === "ArrowLeft" && idx > 0) onPageChange(sorted[idx - 1].page_number);
      else if (e.key === "ArrowRight" && idx >= 0 && idx < sorted.length - 1) onPageChange(sorted[idx + 1].page_number);
      else if ((e.key === "+" || e.key === "=") && view === "image") setZoom(zoomRef.current * 1.25);
      else if (e.key === "-" && view === "image") setZoom(zoomRef.current / 1.25);
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [editing, idx, sorted, onPageChange, view, setZoom]);

  return (
    <section
      aria-label="Source page"
      data-fullscreen={full || undefined}
      className={`flex min-h-0 flex-col bg-surface ${
        full ? "fixed inset-0 z-[70] sm:inset-4 sm:rounded-panel sm:border sm:border-line sm:shadow-pop" : `h-full ${bare ? "" : "rounded-panel border border-line"}`
      }`}
    >
      <header className="flex flex-wrap items-center gap-x-1.5 gap-y-1 border-b border-line px-2 py-1.5 sm:px-3">
        <div className="flex items-center">
          <button
            type="button"
            onClick={() => idx > 0 && onPageChange(sorted[idx - 1].page_number)}
            disabled={idx <= 0 || editing}
            aria-label="Previous page"
            title="Previous page (left arrow)"
            className="btn-ghost h-9 w-9 p-0"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <p className="whitespace-nowrap px-0.5 text-[14px] font-semibold text-ink tabular-nums">
            {page ? `Page ${page.page_number}` : "No pages"}
            {sorted.length > 0 && <span className="font-normal text-ink-3"> of {sorted.length}</span>}
          </p>
          <button
            type="button"
            onClick={() => idx >= 0 && idx < sorted.length - 1 && onPageChange(sorted[idx + 1].page_number)}
            disabled={idx < 0 || idx >= sorted.length - 1 || editing}
            aria-label="Next page"
            title="Next page (right arrow)"
            className="btn-ghost h-9 w-9 p-0"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
        {page && (
          <div className="ml-auto flex items-center gap-1.5">
            <div role="group" aria-label="Show the page as" className="inline-flex rounded-control bg-sunken p-0.5">
              <ToolbarButton active={view === "image"} onClick={() => setChosenView("image")} label="Original page" disabled={!canShowImage || editing}>
                <FileImage className="h-3.5 w-3.5" strokeWidth={1.75} />
                <span className="hidden sm:inline">Page</span>
              </ToolbarButton>
              <ToolbarButton active={view === "text"} onClick={() => setChosenView("text")} label="Extracted text">
                <AlignLeft className="h-3.5 w-3.5" strokeWidth={1.75} />
                <span className="hidden sm:inline">Text</span>
              </ToolbarButton>
            </div>
            {view === "image" && (
              <div role="group" aria-label="Zoom" className="inline-flex items-center rounded-control bg-sunken p-0.5">
                <ToolbarButton onClick={() => setZoom(zoom / 1.25)} label="Zoom out (-)" disabled={zoom <= MIN_ZOOM}>
                  <ZoomOut className="h-3.5 w-3.5" strokeWidth={1.75} />
                </ToolbarButton>
                <ToolbarButton onClick={() => setZoom(1)} label="Fit the page to the panel" active={zoom === 1}>
                  <span className="min-w-[2.4rem] tabular-nums">{zoom === 1 ? "Fit" : `${Math.round(zoom * 100)}%`}</span>
                </ToolbarButton>
                <ToolbarButton onClick={() => setZoom(zoom * 1.25)} label="Zoom in (+)" disabled={zoom >= MAX_ZOOM}>
                  <ZoomIn className="h-3.5 w-3.5" strokeWidth={1.75} />
                </ToolbarButton>
              </div>
            )}
            {highlight && view === "image" && boxes.length > 0 && (
              <button
                type="button"
                onClick={() => {
                  const z = readingZoom(scrollRef.current?.clientWidth ?? 0, boxes);
                  if (z !== zoom) {
                    anchor.current = null;
                    setZoomState(z);
                    window.setTimeout(scrollToFirst, 30);
                  } else scrollToFirst();
                }}
                className="inline-flex h-8 items-center gap-1 rounded-control px-2 text-[12.5px] font-semibold text-accent ring-1 ring-inset ring-accent/30 hover:bg-accent-soft"
                title="Zoom to the highlighted lines"
              >
                <Crosshair className="h-3.5 w-3.5" strokeWidth={1.75} />
                <span className="hidden sm:inline">Highlight</span>
              </button>
            )}
            {canEdit && view === "text" && !editing && (
              <button type="button" onClick={startEdit} className="btn-secondary h-8 px-2.5 text-[12.5px]">
                <Pencil className="h-3.5 w-3.5" strokeWidth={1.75} />
                Edit text
              </button>
            )}
            <button
              type="button"
              onClick={() => setFull((f) => !f)}
              aria-label={full ? "Leave full screen" : "Full screen"}
              title={full ? "Leave full screen (Esc)" : "Full screen"}
              className="btn-ghost h-9 w-9 p-0"
            >
              {full ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
            </button>
            {!bare && !full && (
              <button type="button" onClick={onClose} aria-label="Close source page" className="btn-ghost h-9 w-9 p-0">
                <X className="h-4 w-4" />
              </button>
            )}
          </div>
        )}
      </header>

      {sorted.length > 1 && (
        <nav aria-label="Pages" className="flex gap-1 overflow-x-auto border-b border-line px-2 py-1.5 sm:px-3">
          {sorted.map((p) => {
            const active = p.page_number === page?.page_number;
            return (
              <button
                key={p.id}
                type="button"
                onClick={() => onPageChange(p.page_number)}
                disabled={editing}
                aria-current={active ? "page" : undefined}
                ref={
                  active
                    ? (el) => {
                        // Keep the current page's chip in view inside the strip (never scrolls the page itself).
                        const strip = el?.parentElement;
                        if (el && strip && (el.offsetLeft < strip.scrollLeft || el.offsetLeft + el.offsetWidth > strip.scrollLeft + strip.clientWidth))
                          strip.scrollLeft = el.offsetLeft - strip.clientWidth / 2;
                      }
                    : undefined
                }
                className={`min-w-[2rem] shrink-0 rounded-control px-2 py-1 text-[13px] font-semibold tabular-nums transition-colors ${
                  active ? "bg-accent text-accent-ink" : "text-ink-2 hover:bg-sunken"
                }`}
              >
                {p.page_number}
              </button>
            );
          })}
        </nav>
      )}

      {((page?.quality_status && !page.quality_status.startsWith("SUCCESS")) || page?.is_human_corrected) && (
        <div className="flex flex-wrap items-center gap-1.5 border-b border-line bg-sunken/50 px-3 py-1.5 text-[12.5px] leading-snug text-ink-2" data-testid="correction-line">
          {page?.quality_status && !page.quality_status.startsWith("SUCCESS") && <StatusBadge status={page.quality_status} size="sm" />}
          {page?.is_human_corrected && (
            <>
              <Tag tone="ok" title="A person corrected this page's text">
                <PenLine className="h-3 w-3" /> Corrected
              </Tag>
              {(page.corrected_by_name || page.corrected_at || page.correction_reason) && (
                <span>
                  {page.corrected_by_name ? `by ${page.corrected_by_name}` : ""}
                  {page.corrected_at ? ` on ${correctionDate(page.corrected_at)}` : ""}
                  {page.correction_reason ? `: ${page.correction_reason}` : ""}
                </span>
              )}
            </>
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

      <div
        ref={scrollRef}
        onMouseDown={view === "image" ? onMouseDown : undefined}
        onDoubleClick={view === "image" ? onDoubleClick : undefined}
        className={`relative min-h-0 flex-1 overflow-auto overscroll-contain ${
          view === "image" ? (zoom > 1 ? (dragging ? "cursor-grabbing select-none" : "cursor-grab") : "cursor-zoom-in") : ""
        }`}
        style={view === "image" ? { touchAction: "pan-x pan-y" } : undefined}
      >
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
                            className="absolute origin-left rounded-[2px] bg-marker/55 mix-blend-multiply ring-2 ring-inset ring-marker-edge/60"
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
            ) : editing ? (
              <form onSubmit={saveEdit} className="flex flex-col gap-3">
                {saveError && <Notice kind="error">{saveError}</Notice>}
                {!text && <p className="text-[13px] text-ink-3">Type what the original page says. Use the Page view to check it.</p>}
                <div>
                  <label htmlFor="page-edit-text" className="field-label">
                    Page {page.page_number} text
                  </label>
                  <textarea
                    id="page-edit-text"
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    disabled={saving}
                    rows={10}
                    lang={hasBangla(draft) ? "bn" : undefined}
                    className="field min-h-[28dvh] resize-y text-[14.5px] leading-[1.7]"
                  />
                </div>
                <div>
                  <label htmlFor="page-edit-reason" className="field-label">
                    Reason for the change
                  </label>
                  <input
                    id="page-edit-reason"
                    type="text"
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    disabled={saving}
                    maxLength={300}
                    placeholder="For example: fixed a wrong digit"
                    className="field"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <button type="submit" disabled={saving} className="btn-primary">
                    {saving ? "Saving..." : "Save"}
                  </button>
                  <button type="button" onClick={cancelEdit} disabled={saving} className="btn-secondary">
                    Cancel
                  </button>
                </div>
              </form>
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
                {page.quality_status === "NEEDS_HUMAN_REVIEW" && <p>The text on this page looks damaged. It will be read again from the page image.</p>}
                {page.quality_status === "READ_FAILED" && <p>Every way of reading this page failed, so it has no text yet.</p>}
                {page.vision_error && page.quality_status === "PENDING_VISION" && <p>The last try did not work. It will be tried again soon.</p>}
              </div>
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </section>
  );
}
