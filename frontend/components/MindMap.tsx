"use client";

/**
 * A mind map of one circular, made by itself from its checked points: summary, what changed, requirements
 * (with deadlines), who it applies to, dates, exceptions and related circulars. Only points shown to readers
 * are used, so nothing here is unchecked. Each point opens its source page when tapped.
 *
 * The same drawing is used on screen (`MindMap`) and turned into a picture for emails (`mindMapPng`).
 */
import { useMemo } from "react";
import type { ClaimItem, ClaimSection, DocumentItem } from "@/services/api";

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

/** The branches of a circular's mind map, from the points readers can see. */
export function buildBranches(doc: DocumentItem, shownOf: (s: ClaimSection) => ClaimItem[], entityLabel: (e: any) => string): MindBranch[] {
  const leaf = (item: ClaimItem, text: string): MindLeaf => ({ text, page: item.page_number, item });
  const branches: MindBranch[] = [
    { key: "summary", label: "In short", color: BRANCH_COLORS.summary, leaves: shownOf("summary").map((i) => leaf(i, i.fields.text || "")) },
    { key: "changes", label: "What changed", color: BRANCH_COLORS.changes, leaves: shownOf("changes").map((i) => leaf(i, i.fields.text || "")) },
    {
      key: "requirements",
      label: "What banks must do",
      color: BRANCH_COLORS.requirements,
      leaves: shownOf("requirements").map((i) => {
        const dl = i.fields.deadline ? fmtDate(i.fields.deadline) : i.fields.deadline_text || "";
        return leaf(i, `${i.fields.title || "Requirement"}${dl ? ` (by ${dl})` : ""}`);
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
        ...leaf(i, `${readable(i.link?.shown_type || "mentions")} ${i.link?.target_reference || i.fields.target_hint || "a circular"}`),
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
const LINE = 17;
const LEAF_GAP = 10;
const BRANCH_GAP = 22;
const CHARS_PER_LINE = 62;
const MAX_LINES = 3;
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
  if (lines.length === maxLines && words.join(" ").length > lines.join(" ").length) lines[maxLines - 1] = lines[maxLines - 1].replace(/.{0,2}$/, "") + "…";
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

function layout(branches: MindBranch[]) {
  let y = 20;
  const placed: Placed[] = [];
  for (const b of branches) {
    const shown = b.leaves.slice(0, MAX_LEAVES);
    const leaves: Placed["leaves"] = [];
    const start = y;
    for (const leaf of shown) {
      const lines = wrap(leaf.text);
      const h = lines.length * LINE + 8;
      leaves.push({ leaf, lines, y, h });
      y += h + LEAF_GAP;
    }
    if (b.leaves.length > MAX_LEAVES) {
      leaves.push({ leaf: { text: `+ ${b.leaves.length - MAX_LEAVES} more` }, lines: [`+ ${b.leaves.length - MAX_LEAVES} more in the circular`], y, h: LINE + 8, more: 1 });
      y += LINE + 8 + LEAF_GAP;
    }
    const h = y - LEAF_GAP - start;
    placed.push({ branch: b, y: start, h, leaves });
    y += BRANCH_GAP;
  }
  return { placed, height: Math.max(y, 220) };
}

/** The mind map as one SVG string. `interactive` adds data attributes the screen uses to open pages. */
export function mindMapSvg(doc: DocumentItem, branches: MindBranch[], p: Palette = LIGHT, interactive = false): string {
  const { placed, height } = layout(branches);
  const rootLines = wrap(doc.title.replace(doc.reference_number || "", "").replace(/^[\s:–-]+/, ""), 34, 5);
  const rootH = 34 + rootLines.length * 18 + 14;
  const rootY = Math.max(12, height / 2 - rootH / 2);
  const rootMid = rootY + rootH / 2;
  const parts: string[] = [];
  parts.push(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${height}" width="${W}" height="${height}" font-family="Segoe UI, Roboto, Arial, sans-serif">`);
  parts.push(`<rect width="${W}" height="${height}" fill="${p.bg}"/>`);
  for (const pb of placed) {
    const bMid = pb.y + pb.h / 2;
    const c = pb.branch.color;
    parts.push(
      `<path d="M ${ROOT_X + ROOT_W} ${rootMid} C ${ROOT_X + ROOT_W + 50} ${rootMid}, ${BRANCH_X - 50} ${bMid}, ${BRANCH_X} ${bMid}" fill="none" stroke="${c}" stroke-width="2.5" opacity="0.8"/>`,
    );
    parts.push(`<rect x="${BRANCH_X}" y="${bMid - 17}" width="${BRANCH_W}" height="34" rx="17" fill="${c}"/>`);
    parts.push(`<text x="${BRANCH_X + BRANCH_W / 2}" y="${bMid + 5}" text-anchor="middle" font-size="14" font-weight="600" fill="#ffffff">${esc(pb.branch.label)}</text>`);
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
        parts.push(`<text x="${LEAF_X + 10}" y="${l.y + 18 + i * LINE}" font-size="13" fill="${l.more ? p.ink2 : p.ink}">${esc(line)}</text>`);
      });
      if (l.leaf.page) {
        parts.push(`<text x="${LEAF_X + LEAF_W - 8}" y="${l.y + 15}" text-anchor="end" font-size="10.5" fill="${p.ink2}">p. ${l.leaf.page}</text>`);
      }
      parts.push(`</g>`);
    }
  }
  parts.push(`<rect x="${ROOT_X}" y="${rootY}" width="${ROOT_W}" height="${rootH}" rx="14" fill="${p.rootBg}"/>`);
  parts.push(`<text x="${ROOT_X + 16}" y="${rootY + 26}" font-size="14" font-weight="700" fill="${p.rootInk}">${esc(doc.reference_number || "Circular")}</text>`);
  rootLines.forEach((line, i) => {
    parts.push(`<text x="${ROOT_X + 16}" y="${rootY + 48 + i * 18}" font-size="13.5" fill="${p.rootInk}" opacity="0.92">${esc(line)}</text>`);
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
}: {
  doc: DocumentItem;
  branches: MindBranch[];
  dark?: boolean;
  onOpenLeaf: (leaf: MindLeaf) => void;
}) {
  const palette: Palette = dark ? { bg: "transparent", ink: "#e6ece9", ink2: "#9aa7a1", line: "#33403a", rootBg: "#2f7d63", rootInk: "#ffffff" } : { ...LIGHT, bg: "transparent" };
  const svg = useMemo(() => mindMapSvg(doc, branches, palette, true), [doc, branches, dark]); // eslint-disable-line react-hooks/exhaustive-deps

  if (branches.length === 0) {
    return (
      <p className="p-4 text-[14px] text-ink-3">
        The mind map is made from the checked summary and requirements. This circular has none yet, so there is nothing to draw.
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
    <div
      className="mind-map w-full [&_svg]:h-auto [&_svg]:w-full"
      onClick={pick}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && pick(e)}
      aria-label="Mind map of this circular. Tap a point to open its source page."
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
