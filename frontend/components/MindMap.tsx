"use client";

/**
 * A mind map of one circular, made by itself from its checked points: summary, what changed, requirements
 * (with deadlines), who it applies to, dates, exceptions and related circulars. Only points shown to readers
 * are used, so nothing here is unchecked. Each point opens its source page when tapped.
 *
 * The same drawing is used on screen (`MindMap`) and turned into a picture for emails (`mindMapPng`).
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { Minus, Plus, RotateCcw } from "lucide-react";
import type { ClaimItem, ClaimSection, DocumentItem } from "@/services/api";
import { titleWithoutRef } from "./ui";

export interface MindLeaf {
  text: string;
  page?: number | null;
  item?: ClaimItem;
  docId?: string | null;
}

export interface MindBranch {
  key: string;
  label: string;
  color: string;
  leaves: MindLeaf[];
}

const BRANCH_COLORS: Record<string, string> = {
  summary: "#2f7d63",
  changes: "#8a5cc2",
  requirements: "#c0662c",
  applies_to: "#2f6fb0",
  dates: "#b3382f",
  exemptions: "#7a7a2a",
  links: "#4b6b7a",
};

const fmtDate = (v?: string | null) => {
  if (!v) return "";
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? v : d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
};
const readable = (v?: string | null) => (v ? v.charAt(0) + v.slice(1).toLowerCase().replace(/_/g, " ") : "");
/** A related circular's title, cut at a word when very long (the leaf opens the circular for the rest). */
const shortTitle = (t: string, max = 110) => {
  const s = t.replace(/\s+/g, " ").trim().replace(/[\s.]+$/, "");
  if (s.length <= max) return s;
  const cut = s.slice(0, max);
  return cut.slice(0, cut.lastIndexOf(" ") > 40 ? cut.lastIndexOf(" ") : max).replace(/[\s,;:.\-–]+$/, "") + "…";
};

/** The branches of a circular's mind map, from the points readers can see. */
export function buildBranches(doc: DocumentItem, shownOf: (s: ClaimSection) => ClaimItem[], entityLabel: (e: any) => string): MindBranch[] {
  const leaf = (item: ClaimItem, text: string): MindLeaf => ({ text, page: item.page_number, item });
  const branches: MindBranch[] = [
    // No "In short" branch (owner, 2026-11-26): the summary has its own section right below the map.
    { key: "changes", label: "What changed", color: BRANCH_COLORS.changes, leaves: shownOf("changes").map((i) => leaf(i, i.fields.text || "")) },
    {
      key: "requirements",
      label: "What banks must do",
      color: BRANCH_COLORS.requirements,
      leaves: shownOf("requirements").map((i) => {
        // The duty itself, not just its name (owner, 2026-11-26: a title and a deadline alone are not insightful):
        // "Title: what exactly to do. Who: ... By 31 Dec 2024."
        const dl = i.fields.deadline ? `By ${fmtDate(i.fields.deadline)}.` : i.fields.deadline_text ? `${String(i.fields.deadline_text).trim().replace(/^./, (c) => c.toUpperCase())}.` : "";
        const title = (i.fields.title || "Requirement").trim();
        let desc = String(i.fields.description || "").trim();
        if (desc.toLowerCase().startsWith(title.toLowerCase())) desc = desc.slice(title.length).replace(/^[\s:,.-]+/, "");
        const who = i.fields.who ? `Who: ${String(i.fields.who).trim().replace(/\.$/, "")}.` : "";
        return leaf(i, [desc ? `${title}: ${desc}` : title, who, dl].filter(Boolean).join(" "));
      }),
    },
    { key: "applies_to", label: "Who it applies to", color: BRANCH_COLORS.applies_to, leaves: shownOf("applies_to").map((i) => leaf(i, entityLabel(i.fields.entity))) },
    {
      key: "dates",
      label: "Key dates",
      color: BRANCH_COLORS.dates,
      leaves: [
        { text: `Issued ${fmtDate(doc.publication_date)}` },
        ...shownOf("dates")
          .filter((i) => i.fields.date)
          .map((i) => leaf(i, `${readable(i.fields.date_kind)}: ${fmtDate(i.fields.date)}`)),
      ],
    },
    { key: "exemptions", label: "Exceptions", color: BRANCH_COLORS.exemptions, leaves: shownOf("exemptions").map((i) => leaf(i, i.fields.text || "")) },
    {
      key: "links",
      label: "Related circulars",
      color: BRANCH_COLORS.links,
      leaves: shownOf("links").map((i) => ({
        // The related circular's title leads ("Repeals: Inclusion of ..."); its number only when no title is known.
        ...leaf(
          i,
          i.link?.target_title
            ? `${readable(i.link.shown_type || "mentions")}: ${shortTitle(i.link.target_title)}`
            : `${readable(i.link?.shown_type || "mentions")} ${i.link?.target_reference || i.fields.target_hint || "a circular"}`,
        ),
        docId: i.link?.target_document_id ?? null,
      })),
    },
  ];
  return branches.filter((b) => b.leaves.length > 0 && b.leaves.some((l) => l.text.trim()));
}

// ------------------------------------------------------------------------------- layout

const W = 1000;
const ROOT_X = 24;
const ROOT_W = 250;
const BRANCH_X = 330;
const BRANCH_W = 170;
const LEAF_X = 540;
const LEAF_W = W - LEAF_X - 16;
const LINE = 21;
const LEAF_GAP = 10;
const BRANCH_GAP = 22;
const CHARS_PER_LINE = 54;
const MAX_LINES = 4;
const MAX_LEAVES = 8;

function wrap(text: string, width = CHARS_PER_LINE, maxLines = MAX_LINES): string[] {
  const words = text.replace(/\s+/g, " ").trim().split(" ");
  const lines: string[] = [];
  let cur = "";
  for (const w of words) {
    if ((cur + " " + w).trim().length > width) {
      if (cur) lines.push(cur);
      cur = w;
      if (lines.length === maxLines) break;
    } else cur = (cur + " " + w).trim();
  }
  if (lines.length < maxLines && cur) lines.push(cur);
  if (lines.length === maxLines && words.join(" ").length > lines.join(" ").length) {
    // Cut at a word, never inside one.
    const last = lines[maxLines - 1];
    const room = last.length > width - 2 ? last.slice(0, last.lastIndexOf(" ")) : last;
    lines[maxLines - 1] = room.replace(/[\s,;:.\-–]+$/, "") + "…";
  }
  return lines;
}

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

export interface Palette {
  bg: string;
  ink: string;
  ink2: string;
  line: string;
  rootBg: string;
  rootInk: string;
}

export const LIGHT: Palette = { bg: "#ffffff", ink: "#1b2420", ink2: "#4a5550", line: "#d5dbd8", rootBg: "#1f5c47", rootInk: "#ffffff" };

interface Placed {
  branch: MindBranch;
  y: number;
  h: number;
  leaves: { leaf: MindLeaf; lines: string[]; y: number; h: number; more?: number }[];
}

function layout(branches: MindBranch[], full = false) {
  let y = 20;
  const placed: Placed[] = [];
  for (const b of branches) {
    const shown = full ? b.leaves : b.leaves.slice(0, MAX_LEAVES);
    const leaves: Placed["leaves"] = [];
    const start = y;
    for (const leaf of shown) {
      const lines = wrap(leaf.text, CHARS_PER_LINE, full ? 99 : MAX_LINES);
      // A small line under the text for "p. 3" (and "· Analysing" while the point is still being checked).
      const h = lines.length * LINE + 12 + (leaf.page ? 18 : 0);
      leaves.push({ leaf, lines, y, h });
      y += h + LEAF_GAP;
    }
    if (!full && b.leaves.length > MAX_LEAVES) {
      leaves.push({ leaf: { text: `+ ${b.leaves.length - MAX_LEAVES} more` }, lines: [`+ ${b.leaves.length - MAX_LEAVES} more in the circular`], y, h: LINE + 8, more: 1 });
      y += LINE + 8 + LEAF_GAP;
    }
    const h = y - LEAF_GAP - start;
    placed.push({ branch: b, y: start, h, leaves });
    y += BRANCH_GAP;
  }
  return { placed, height: Math.max(y, 220) };
}

/** The mind map as one SVG string. `interactive` adds data attributes the screen uses to open pages;
 * `full` draws every point in full (no "+ N more", no cut-off text). */
export function mindMapSvg(doc: DocumentItem, branches: MindBranch[], p: Palette = LIGHT, interactive = false, full = false): string {
  const { placed, height } = layout(branches, full);
  const rootLines = wrap(titleWithoutRef(doc.title, doc.reference_number), 34, 5);
  const rootH = 38 + rootLines.length * 20 + 14;
  // Centred on short maps; on tall ones it stays near the top so it is in view when the map opens.
  const rootY = Math.max(12, Math.min(height / 2 - rootH / 2, 150));
  const rootMid = rootY + rootH / 2;
  const parts: string[] = [];
  parts.push(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${height}" width="${W}" height="${height}" font-family="Source Sans 3, Segoe UI, Roboto, Noto Sans Bengali, Arial, sans-serif">`);
  parts.push(`<rect width="${W}" height="${height}" fill="${p.bg}"/>`);
  // One trunk from the circular down (and up) past every branch, with a short coloured arm to each:
  // no bundle of overlapping curves on tall maps.
  const trunkX = ROOT_X + ROOT_W + 36;
  const mids = placed.map((pb) => pb.y + pb.h / 2);
  const top = Math.min(rootMid, ...mids);
  const bottom = Math.max(rootMid, ...mids);
  parts.push(`<path d="M ${ROOT_X + ROOT_W} ${rootMid} H ${trunkX}" fill="none" stroke="${p.ink2}" stroke-width="2" opacity="0.55"/>`);
  if (bottom - top > 1) {
    parts.push(`<path d="M ${trunkX} ${top + 10} V ${bottom - 10}" fill="none" stroke="${p.ink2}" stroke-width="2" opacity="0.55"/>`);
  }
  for (const pb of placed) {
    const bMid = pb.y + pb.h / 2;
    const c = pb.branch.color;
    const r = Math.min(10, Math.abs(bMid - rootMid));
    const dir = bMid < rootMid ? -1 : 1;
    const arm =
      r < 1
        ? `M ${trunkX} ${bMid} H ${BRANCH_X}`
        : `M ${trunkX} ${bMid - dir * r} Q ${trunkX} ${bMid}, ${trunkX + r} ${bMid} H ${BRANCH_X}`;
    parts.push(`<path d="${arm}" fill="none" stroke="${c}" stroke-width="2.5" opacity="0.85"/>`);
    parts.push(`<rect x="${BRANCH_X}" y="${bMid - 17}" width="${BRANCH_W}" height="34" rx="17" fill="${c}"/>`);
    parts.push(`<text x="${BRANCH_X + BRANCH_W / 2}" y="${bMid + 5}" text-anchor="middle" font-size="16" font-weight="600" fill="#ffffff">${esc(pb.branch.label)}</text>`);
    for (const l of pb.leaves) {
      const lMid = l.y + l.h / 2;
      parts.push(
        `<path d="M ${BRANCH_X + BRANCH_W} ${bMid} C ${BRANCH_X + BRANCH_W + 25} ${bMid}, ${LEAF_X - 25} ${lMid}, ${LEAF_X} ${lMid}" fill="none" stroke="${c}" stroke-width="1.5" opacity="0.6"/>`,
      );
      const clickable = interactive && !l.more && (l.leaf.page || l.leaf.docId);
      const attrs = clickable
        ? ` data-branch="${esc(pb.branch.key)}" data-leaf="${pb.leaves.indexOf(l)}" style="cursor:pointer" role="button" tabindex="0"`
        : "";
      parts.push(`<g${attrs}>`);
      parts.push(`<rect x="${LEAF_X}" y="${l.y}" width="${LEAF_W}" height="${l.h}" rx="8" fill="${c}" fill-opacity="0.09" stroke="${c}" stroke-opacity="0.35"/>`);
      l.lines.forEach((line, i) => {
        parts.push(`<text x="${LEAF_X + 12}" y="${l.y + 21 + i * LINE}" font-size="15" fill="${l.more ? p.ink2 : p.ink}">${esc(line)}</text>`);
      });
      if (l.leaf.page) {
        parts.push(`<text x="${LEAF_X + 12}" y="${l.y + 21 + l.lines.length * LINE}" font-size="12" fill="${p.ink2}">Page ${l.leaf.page}${l.leaf.item?.check_page ? " · Analysing" : ""}</text>`);
      }
      parts.push(`</g>`);
    }
  }
  parts.push(`<rect x="${ROOT_X}" y="${rootY}" width="${ROOT_W}" height="${rootH}" rx="14" fill="${p.rootBg}"/>`);
  parts.push(`<text x="${ROOT_X + 16}" y="${rootY + 26}" font-size="16" font-weight="700" fill="${p.rootInk}">${esc(doc.reference_number || "Circular")}</text>`);
  rootLines.forEach((line, i) => {
    parts.push(`<text x="${ROOT_X + 16}" y="${rootY + 50 + i * 20}" font-size="15" fill="${p.rootInk}" opacity="0.92">${esc(line)}</text>`);
  });
  parts.push(`</svg>`);
  return parts.join("");
}

// ------------------------------------------------------------------------- narrow layout

const N_TRUNK = 24;
const N_PILL_X = 40;
const N_LEAF_X = 58;
const N_LINE = 22;

/** The same map drawn top to bottom, for phones and narrow panes: it fits the width, so nothing scrolls sideways. */
export function mindMapSvgNarrow(doc: DocumentItem, branches: MindBranch[], p: Palette = LIGHT, interactive = false, full = false, width = 360): string {
  // Drawn at the width it is shown at (no shrinking), so the text is always 15-16 px on screen.
  const NW = Math.max(320, Math.round(width));
  const N_LEAF_W = NW - N_LEAF_X - 10;
  const N_CHARS = Math.max(26, Math.floor((N_LEAF_W - 24) / 7.4));
  const rootLines = wrap(titleWithoutRef(doc.title, doc.reference_number), Math.floor((NW - 48) / 7.6), full ? 8 : 5);
  const rootY = 10;
  const rootH = 36 + rootLines.length * 21 + 12;
  let y = rootY + rootH + 20;
  const body: string[] = [];
  let lastMid = rootY + rootH;
  for (const b of branches) {
    const c = b.color;
    const pillW = Math.min(NW - N_PILL_X - 10, b.label.length * 9 + 36);
    const pMid = y + 17;
    lastMid = pMid;
    body.push(`<path d="M ${N_TRUNK} ${pMid} H ${N_PILL_X}" fill="none" stroke="${c}" stroke-width="2.5" opacity="0.85"/>`);
    body.push(`<rect x="${N_PILL_X}" y="${y}" width="${pillW}" height="34" rx="17" fill="${c}"/>`);
    body.push(`<text x="${N_PILL_X + pillW / 2}" y="${pMid + 6}" text-anchor="middle" font-size="16" font-weight="600" fill="#ffffff">${esc(b.label)}</text>`);
    y += 34 + 10;
    const shown = full ? b.leaves : b.leaves.slice(0, MAX_LEAVES);
    const items: { leaf: MindLeaf; idx: number; more?: boolean }[] = shown.map((leaf, idx) => ({ leaf, idx }));
    if (!full && b.leaves.length > MAX_LEAVES) items.push({ leaf: { text: `+ ${b.leaves.length - MAX_LEAVES} more in the circular` }, idx: -1, more: true });
    const stemTop = y - 8;
    let stemBottom = stemTop;
    const stemX = N_PILL_X + 10;
    for (const it of items) {
      const lines = wrap(it.leaf.text, N_CHARS, full ? 99 : MAX_LINES);
      const h = lines.length * N_LINE + 14 + (it.leaf.page ? 18 : 0);
      const lMid = y + Math.min(h / 2, 19);
      stemBottom = lMid;
      body.push(`<path d="M ${stemX} ${lMid} H ${N_LEAF_X}" fill="none" stroke="${c}" stroke-width="1.5" opacity="0.6"/>`);
      const clickable = interactive && !it.more && (it.leaf.page || it.leaf.docId);
      const attrs = clickable ? ` data-branch="${esc(b.key)}" data-leaf="${it.idx}" style="cursor:pointer" role="button" tabindex="0"` : "";
      body.push(`<g${attrs}>`);
      body.push(`<rect x="${N_LEAF_X}" y="${y}" width="${N_LEAF_W}" height="${h}" rx="8" fill="${c}" fill-opacity="0.09" stroke="${c}" stroke-opacity="0.35"/>`);
      lines.forEach((line, i) => {
        body.push(`<text x="${N_LEAF_X + 12}" y="${y + 23 + i * N_LINE}" font-size="15" fill="${it.more ? p.ink2 : p.ink}">${esc(line)}</text>`);
      });
      if (it.leaf.page) {
        body.push(`<text x="${N_LEAF_X + 12}" y="${y + 21 + lines.length * N_LINE}" font-size="12" fill="${p.ink2}">Page ${it.leaf.page}${it.leaf.item?.check_page ? " · Analysing" : ""}</text>`);
      }
      body.push(`</g>`);
      y += h + 10;
    }
    if (items.length) body.unshift(`<path d="M ${stemX} ${stemTop} V ${stemBottom}" fill="none" stroke="${c}" stroke-width="1.5" opacity="0.6"/>`);
    y += 14;
  }
  const height = Math.max(y, 160);
  const parts: string[] = [];
  parts.push(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${NW} ${height}" width="${NW}" height="${height}" font-family="Source Sans 3, Segoe UI, Roboto, Noto Sans Bengali, Arial, sans-serif">`);
  parts.push(`<rect width="${NW}" height="${height}" fill="${p.bg}"/>`);
  parts.push(`<path d="M ${N_TRUNK} ${rootY + rootH} V ${lastMid}" fill="none" stroke="${p.ink2}" stroke-width="2" opacity="0.55"/>`);
  parts.push(...body);
  parts.push(`<rect x="10" y="${rootY}" width="${NW - 20}" height="${rootH}" rx="12" fill="${p.rootBg}"/>`);
  parts.push(`<text x="24" y="${rootY + 27}" font-size="16" font-weight="700" fill="${p.rootInk}">${esc(doc.reference_number || "Circular")}</text>`);
  rootLines.forEach((line, i) => {
    parts.push(`<text x="24" y="${rootY + 51 + i * 21}" font-size="15" fill="${p.rootInk}" opacity="0.92">${esc(line)}</text>`);
  });
  parts.push(`</svg>`);
  return parts.join("");
}

/** The mind map as a PNG data URL (for emails). */
export async function mindMapPng(doc: DocumentItem, branches: MindBranch[]): Promise<string | null> {
  if (branches.length === 0) return null;
  const svg = mindMapSvg(doc, branches, LIGHT);
  const { height } = layout(branches);
  const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
  try {
    const img = new Image();
    await new Promise<void>((res, rej) => {
      img.onload = () => res();
      img.onerror = () => rej(new Error("Could not draw the mind map."));
      img.src = url;
    });
    const scale = 1.5;
    const canvas = document.createElement("canvas");
    canvas.width = W * scale;
    canvas.height = height * scale;
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;
    ctx.scale(scale, scale);
    ctx.drawImage(img, 0, 0);
    return canvas.toDataURL("image/png");
  } finally {
    URL.revokeObjectURL(url);
  }
}

export default function MindMap({
  doc,
  branches,
  dark,
  onOpenLeaf,
  full,
}: {
  doc: DocumentItem;
  branches: MindBranch[];
  dark?: boolean;
  onOpenLeaf: (leaf: MindLeaf) => void;
  /** Every point in full and no inner scroll box (the inline map at the top of a circular). */
  full?: boolean;
}) {
  const palette: Palette = dark ? { bg: "transparent", ink: "#e6ece9", ink2: "#9aa7a1", line: "#33403a", rootBg: "#2f7d63", rootInk: "#ffffff" } : { ...LIGHT, bg: "transparent" };
  // Narrow spaces (phones, the reader beside an open side panel) get the top-to-bottom drawing that fits the width.
  const box = useRef<HTMLDivElement>(null);
  // The wide drawing is 1000 units wide: shown narrower than about 900 px its text would shrink below reading size,
  // so smaller spaces get the top-to-bottom drawing made at the exact width of the space.
  const [boxW, setBoxW] = useState(() => (typeof window !== "undefined" ? Math.min(window.innerWidth - 32, 1000) : 1000));
  useEffect(() => {
    const el = box.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([e]) => setBoxW(Math.round(e.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const narrow = boxW < 900;
  // Re-drawn only when the width changes by a step, not on every pixel of a resize.
  const narrowW = Math.max(320, Math.floor(boxW / 20) * 20);
  const svg = useMemo(
    () => (narrow ? mindMapSvgNarrow(doc, branches, palette, true, full, narrowW) : mindMapSvg(doc, branches, palette, true, full)),
    [doc, branches, dark, full, narrow, narrowW], // eslint-disable-line react-hooks/exhaustive-deps
  );
  const [zoom, setZoom] = useState(1);
  useEffect(() => setZoom(1), [narrow]);
  const pane = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; y: number; left: number; top: number; moved: boolean } | null>(null);

  if (branches.length === 0) {
    return (
      <p className="p-4 text-[14px] text-ink-3">
        The mind map is made from the checked requirements and other points. This circular has none yet, so there is nothing to draw.
      </p>
    );
  }

  const pick = (e: React.SyntheticEvent) => {
    const g = (e.target as Element).closest("[data-branch]");
    if (!g) return;
    const b = branches.find((x) => x.key === g.getAttribute("data-branch"));
    const leaf = b?.leaves[Number(g.getAttribute("data-leaf"))];
    if (leaf) onOpenLeaf(leaf);
  };

  return (
    <div ref={box} className="space-y-2">
      {/* Zoom (buttons) and pan (scroll, or drag with the mouse) for large maps; above the map so they never cover it.
          The narrow drawing already fits the width and needs no zoom. */}
      {!narrow && (
        <div className="flex justify-end">
          <div className="flex gap-1 rounded-control border border-line bg-surface p-0.5">
            <button type="button" aria-label="Zoom out" disabled={zoom <= 1} onClick={() => setZoom((z) => Math.max(1, +(z - 0.25).toFixed(2)))} className="grid h-8 w-8 place-items-center rounded text-ink-2 hover:bg-sunken disabled:opacity-40">
              <Minus className="h-4 w-4" />
            </button>
            <span className="grid min-w-[3rem] place-items-center text-[12.5px] tabular-nums text-ink-3">{Math.round(zoom * 100)}%</span>
            <button type="button" aria-label="Zoom in" disabled={zoom >= 2.5} onClick={() => setZoom((z) => Math.min(2.5, +(z + 0.25).toFixed(2)))} className="grid h-8 w-8 place-items-center rounded text-ink-2 hover:bg-sunken disabled:opacity-40">
              <Plus className="h-4 w-4" />
            </button>
            <button type="button" aria-label="Reset zoom" disabled={zoom === 1} onClick={() => setZoom(1)} className="grid h-8 w-8 place-items-center rounded text-ink-2 hover:bg-sunken disabled:opacity-40">
              <RotateCcw className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      )}
      <div>
          <div
            ref={pane}
            className={`${narrow ? "" : "-mx-4 px-4 sm:mx-0 sm:px-0 "}${full ? "" : "max-h-[72vh] "}overflow-auto ${zoom > 1 ? "cursor-grab active:cursor-grabbing" : ""}`}
            onPointerDown={(e) => {
              if (zoom <= 1 || e.pointerType !== "mouse" || !pane.current) return;
              drag.current = { x: e.clientX, y: e.clientY, left: pane.current.scrollLeft, top: pane.current.scrollTop, moved: false };
            }}
            onPointerMove={(e) => {
              const d = drag.current;
              if (!d || !pane.current) return;
              if (Math.abs(e.clientX - d.x) + Math.abs(e.clientY - d.y) > 4) d.moved = true;
              pane.current.scrollLeft = d.left - (e.clientX - d.x);
              pane.current.scrollTop = d.top - (e.clientY - d.y);
            }}
            onPointerUp={() => {
              setTimeout(() => (drag.current = null), 0);
            }}
            onPointerLeave={() => (drag.current = null)}
          >
            <div
              className="mind-map [&_svg]:h-auto [&_svg]:w-full"
              style={narrow ? { width: `${narrowW}px`, maxWidth: "100%" } : { minWidth: `${1000 * zoom}px`, width: `${100 * zoom}%` }}
              onClick={(e) => {
                if (drag.current?.moved) return;
                pick(e);
              }}
              onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && pick(e)}
              aria-label="Mind map of this circular. Tap a point to open its source page."
              dangerouslySetInnerHTML={{ __html: svg }}
            />
          </div>
        </div>
    </div>
  );
}
