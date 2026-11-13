"use client";

import { useMemo } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { BookOpenText, Check, Clock, X } from "lucide-react";
import type { DocumentRef, RelGraph, RelGraphEdge, RelGraphNode, RelLink, RelTimeline } from "@/services/api";
import { reviewLink, useRelState } from "@/services/relationshipsStore";
import { AwaitingReviewTag, InForceBadge, Tag } from "./StatusBadge";
import { hasBangla } from "./ui";

export const REL_LABEL: Record<string, string> = {
  AMENDS: "Amends",
  REPEALS: "Repeals",
  SUPERSEDES: "Supersedes",
  REPLACES: "Replaces",
  CLARIFIES: "Clarifies",
  REFERENCES: "Refers to",
  IMPLEMENTS: "Implements",
  RELATED_TO: "Related to",
};

export function relLabel(type: string) {
  return REL_LABEL[type] ?? type.charAt(0) + type.slice(1).toLowerCase().replace(/_/g, " ");
}

export function shortDate(value?: string | null) {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

/** The circular a link points at: its number, or the cited number that is not in the library. */
export function targetLabel(link: Pick<RelLink, "target" | "target_reference_hint">) {
  return link.target?.reference_number || link.target?.title || link.target_reference_hint || "a cited circular";
}

/** Opens the page a quote is printed on, in the reader. */
export function quoteHref(link: Pick<RelLink, "source" | "page_number">) {
  return link.page_number ? `/?doc=${link.source.id}&page=${link.page_number}` : `/?doc=${link.source.id}`;
}

export function PageQuoteLink({ link }: { link: Pick<RelLink, "source" | "page_number"> }) {
  if (!link.page_number) return <span className="text-[12.5px] text-ink-3">Page not linked</span>;
  return (
    <Link
      href={quoteHref(link)}
      title={`Open page ${link.page_number} of ${link.source.reference_number || "the circular"} to read the quote in place`}
      className="inline-flex items-center gap-1 rounded-control px-1.5 py-0.5 text-[12.5px] font-semibold text-accent ring-1 ring-inset ring-accent/25 transition-colors hover:bg-accent-soft"
    >
      <BookOpenText className="h-3.5 w-3.5" strokeWidth={1.75} />
      Page {link.page_number}
    </Link>
  );
}

/** Approve / reject buttons for an unconfirmed link. Administrators only. */
export function ReviewButtons({ link, compact = false }: { link: RelLink; compact?: boolean }) {
  const { busy } = useRelState();
  const working = busy[link.id];
  return (
    <div className="flex flex-wrap items-center gap-2">
      <button type="button" onClick={() => void reviewLink(link, "VERIFIED")} disabled={!!working} className={`btn-primary ${compact ? "py-1" : ""}`}>
        <Check className="h-3.5 w-3.5" strokeWidth={2.25} />
        {working === "VERIFIED" ? "Saving..." : "Approve"}
      </button>
      <button type="button" onClick={() => void reviewLink(link, "REJECTED")} disabled={!!working} className={`btn-danger ${compact ? "py-1" : ""}`}>
        <X className="h-3.5 w-3.5" strokeWidth={2.25} />
        {working === "REJECTED" ? "Saving..." : "Reject"}
      </button>
    </div>
  );
}

/** One link: what it does, to which circular, the exact quote, and the page it is on. */
export function LinkCard({ link, isAdmin, perspective }: { link: RelLink; isAdmin?: boolean; perspective?: "source" | "target" }) {
  const pending = link.verification_status === "PENDING_REVIEW";
  return (
    <div
      className={`space-y-2 rounded-panel border px-3.5 py-3 ${pending ? "border-dashed border-line-strong bg-sunken/40" : "border-line bg-surface"}`}
      data-testid="link-card"
      data-status={link.verification_status}
    >
      <div className="flex flex-wrap items-center gap-2 text-[14px]">
        {perspective !== "source" && (
          <Link href={`/?doc=${link.source.id}`} className="refno hover:underline">
            {link.source.reference_number || "Circular"}
          </Link>
        )}
        <Tag tone={pending ? "muted" : "info"}>{relLabel(link.relationship_type)}</Tag>
        {link.target ? (
          <Link href={`/?doc=${link.target.id}`} className="refno hover:underline">
            {link.target.reference_number || link.target.title}
          </Link>
        ) : (
          <span className="inline-flex items-center gap-1.5 text-ink-2">
            {link.target_reference_hint || "a cited circular"}
            <Tag tone="muted" title="This circular is not in the library yet">
              Not in library
            </Tag>
          </span>
        )}
        {pending && <AwaitingReviewTag />}
      </div>
      {link.supporting_quote && (
        <blockquote className="quote max-w-prose" lang={hasBangla(link.supporting_quote) ? "bn" : undefined}>
          &ldquo;{link.supporting_quote}&rdquo;
        </blockquote>
      )}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <PageQuoteLink link={link} />
        {isAdmin && pending && <ReviewButtons link={link} compact />}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------------- timeline

export function LinksTimeline({ timeline, isAdmin }: { timeline: RelTimeline; isAdmin: boolean }) {
  const { inForce } = useRelState();
  return (
    <ol className="relative space-y-5 border-l border-line-strong pl-6" data-testid="timeline">
      {timeline.items.map((item) => {
        const info = inForce[item.document.id] ?? (item.document.in_force_status ? { status: item.document.in_force_status } : undefined);
        const original = item.changes.length === 0;
        return (
          <li key={item.document.id} className="relative" data-testid="timeline-item">
            <span
              aria-hidden
              className={`absolute -left-[31px] top-1.5 h-3 w-3 rounded-full border-2 ${
                item.is_current ? "border-accent bg-accent" : item.is_selected ? "border-accent bg-surface" : "border-line-strong bg-surface"
              }`}
            />
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[13px] text-ink-3 tabular-nums">{shortDate(item.document.publication_date)}</span>
              <Link href={`/?doc=${item.document.id}`} className="refno hover:underline">
                {item.document.reference_number || "Circular"}
              </Link>
              <InForceBadge info={info ? { status: info.status } : undefined} size="sm" plain />
              {item.is_selected && <Tag tone="accent">This circular</Tag>}
              {item.is_current && <Tag tone="ok">Current version</Tag>}
            </div>
            <p className="mt-0.5 max-w-prose text-[14px] text-ink-2">{item.document.title}</p>
            {original ? (
              <p className="mt-1.5 text-[13px] text-ink-3">Original text. It does not change an earlier circular.</p>
            ) : (
              <div className="mt-2 space-y-2">
                {item.changes.map((c) => (
                  <LinkCard key={c.id} link={c} isAdmin={isAdmin} perspective="source" />
                ))}
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
}

// ---------------------------------------------------------------------------------- graph

const NODE_W = 196;
const NODE_H = 60;
const COL_GAP = 150;
const ROW_GAP = 26;
const PAD = 20;

const STATUS_STYLE: Record<string, { fill: string; stroke: string; label: string }> = {
  IN_FORCE: { fill: "rgb(var(--ok-soft))", stroke: "rgb(var(--ok) / 0.6)", label: "In force" },
  AMENDED: { fill: "rgb(var(--info-soft))", stroke: "rgb(var(--info) / 0.6)", label: "Amended" },
  REPLACED: { fill: "rgb(var(--warn-soft))", stroke: "rgb(var(--warn) / 0.6)", label: "Replaced" },
  REPEALED: { fill: "rgb(var(--bad-soft))", stroke: "rgb(var(--bad) / 0.6)", label: "Repealed" },
};
const NOT_IN_LIBRARY = { fill: "rgb(var(--muted-soft))", stroke: "rgb(var(--line-strong))", label: "Not in library" };

function clip(text: string, n: number) {
  return text.length > n ? `${text.slice(0, n - 1)}…` : text;
}

interface Placed {
  node: RelGraphNode;
  x: number;
  y: number;
}

function layout(graph: RelGraph) {
  const outgoing = new Map<string, string[]>();
  graph.edges.forEach((e) => outgoing.set(e.source, [...(outgoing.get(e.source) ?? []), e.target]));
  const memo = new Map<string, number>();
  const visiting = new Set<string>();
  // Older circulars sit to the left: a circular is one column right of the newest thing it points at.
  const layerOf = (key: string): number => {
    if (memo.has(key)) return memo.get(key)!;
    if (visiting.has(key)) return 0;
    visiting.add(key);
    const next = outgoing.get(key) ?? [];
    const layer = next.length === 0 ? 0 : 1 + Math.max(...next.map(layerOf));
    visiting.delete(key);
    memo.set(key, layer);
    return layer;
  };
  const columns = new Map<number, RelGraphNode[]>();
  graph.nodes.forEach((n) => {
    const l = layerOf(n.key);
    columns.set(l, [...(columns.get(l) ?? []), n]);
  });
  const placed = new Map<string, Placed>();
  let maxRows = 1;
  const maxLayer = Math.max(0, ...Array.from(columns.keys()));
  columns.forEach((nodes, layer) => {
    nodes.sort((a, b) => (a.publication_date || "").localeCompare(b.publication_date || "") || a.key.localeCompare(b.key));
    maxRows = Math.max(maxRows, nodes.length);
    nodes.forEach((node, i) => placed.set(node.key, { node, x: PAD + layer * (NODE_W + COL_GAP), y: PAD + i * (NODE_H + ROW_GAP) }));
  });
  return {
    placed,
    width: PAD * 2 + (maxLayer + 1) * NODE_W + maxLayer * COL_GAP,
    height: PAD * 2 + maxRows * NODE_H + (maxRows - 1) * ROW_GAP + 18,
  };
}

export function edgeToLink(edge: RelGraphEdge, nodes: RelGraphNode[]): RelLink | null {
  const byKey = new Map(nodes.map((n) => [n.key, n]));
  const src = byKey.get(edge.source);
  if (!src || !src.document_id) return null;
  const toRef = (n: RelGraphNode): DocumentRef => ({
    id: n.document_id as string,
    reference_number: n.reference_number,
    title: n.title,
    publication_date: n.publication_date,
    current_version_id: n.current_version_id,
    is_private: n.is_private,
    in_force_status: n.in_force_status,
  });
  const tgt = byKey.get(edge.target);
  return {
    id: edge.id,
    relationship_type: edge.relationship_type,
    verification_status: edge.verification_status,
    confidence: edge.confidence,
    supporting_quote: edge.supporting_quote,
    page_number: edge.page_number,
    source_version_id: edge.source_version_id,
    source: toRef(src),
    target: tgt && tgt.in_library && tgt.document_id ? toRef(tgt) : null,
    target_reference_hint: edge.target_reference_hint,
  };
}

export function LinksGraph({ graph, selectedEdgeId, onSelectEdge }: { graph: RelGraph; selectedEdgeId: string | null; onSelectEdge: (id: string | null) => void }) {
  const router = useRouter();
  const { placed, width, height } = useMemo(() => layout(graph), [graph]);

  const openNode = (n: RelGraphNode) => {
    if (n.in_library && n.document_id) router.push(`/?doc=${n.document_id}`);
  };

  return (
    <div className="overflow-auto rounded-panel border border-line bg-surface" data-testid="graph-scroll">
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="group" aria-label="Relationship graph" className="block" data-testid="graph">
        <defs>
          <marker id="rel-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0 0 L10 5 L0 10 z" style={{ fill: "rgb(var(--ink-3))" }} />
          </marker>
          <marker id="rel-arrow-sel" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0 0 L10 5 L0 10 z" style={{ fill: "rgb(var(--accent))" }} />
          </marker>
        </defs>

        {graph.edges.map((e) => {
          const s = placed.get(e.source);
          const t = placed.get(e.target);
          if (!s || !t) return null;
          const pending = e.verification_status === "PENDING_REVIEW";
          const selected = selectedEdgeId === e.id;
          const sx = s.x;
          const sy = s.y + NODE_H / 2;
          const tx = t.x + NODE_W;
          const ty = t.y + NODE_H / 2;
          let d: string;
          let lx: number;
          let ly: number;
          if (s.x > t.x) {
            const dx = Math.max(40, (sx - tx) / 2);
            d = `M ${sx} ${sy} C ${sx - dx} ${sy}, ${tx + dx} ${ty}, ${tx} ${ty}`;
            lx = (sx + tx) / 2;
            ly = (sy + ty) / 2;
          } else {
            // Same column or backwards (a loop): arc below the nodes.
            const x1 = s.x + NODE_W / 2;
            const x2 = t.x + NODE_W / 2;
            const y = Math.max(s.y, t.y) + NODE_H;
            d = `M ${x1} ${y} Q ${(x1 + x2) / 2} ${y + 46} ${x2} ${y}`;
            lx = (x1 + x2) / 2;
            ly = y + 24;
          }
          const label = relLabel(e.relationship_type);
          const labelW = label.length * 6.6 + 14;
          return (
            <g key={e.id} data-testid="graph-edge" data-status={e.verification_status} data-type={e.relationship_type}>
              <path
                d={d}
                fill="none"
                strokeWidth={selected ? 2.5 : 1.6}
                strokeDasharray={pending ? "6 5" : undefined}
                markerEnd={selected ? "url(#rel-arrow-sel)" : "url(#rel-arrow)"}
                style={{ stroke: selected ? "rgb(var(--accent))" : pending ? "rgb(var(--ink-3) / 0.8)" : "rgb(var(--ink-2))" }}
              />
              <path d={d} fill="none" stroke="transparent" strokeWidth={14} className="cursor-pointer" onClick={() => onSelectEdge(selected ? null : e.id)} />
              <g
                className="cursor-pointer"
                role="button"
                tabIndex={0}
                aria-label={`${label}${pending ? ", awaiting review" : ""}. Show its quote.`}
                onClick={() => onSelectEdge(selected ? null : e.id)}
                onKeyDown={(ev) => {
                  if (ev.key === "Enter" || ev.key === " ") {
                    ev.preventDefault();
                    onSelectEdge(selected ? null : e.id);
                  }
                }}
              >
                <rect
                  x={lx - labelW / 2}
                  y={ly - 10}
                  width={labelW}
                  height={20}
                  rx={10}
                  strokeDasharray={pending ? "3 3" : undefined}
                  style={{ fill: "rgb(var(--surface))", stroke: selected ? "rgb(var(--accent))" : "rgb(var(--line-strong))" }}
                />
                <text x={lx} y={ly + 4} textAnchor="middle" fontSize={11.5} fontWeight={600} style={{ fill: "rgb(var(--ink-2))" }}>
                  {label}
                </text>
              </g>
            </g>
          );
        })}

        {Array.from(placed.values()).map(({ node, x, y }) => {
          const style = !node.in_library ? NOT_IN_LIBRARY : STATUS_STYLE[node.in_force_status || "IN_FORCE"] ?? STATUS_STYLE.IN_FORCE;
          const clickable = node.in_library && !!node.document_id;
          return (
            <g
              key={node.key}
              data-testid="graph-node"
              data-status={node.in_library ? node.in_force_status : "NOT_IN_LIBRARY"}
              transform={`translate(${x},${y})`}
              className={clickable ? "cursor-pointer" : ""}
              role={clickable ? "link" : undefined}
              tabIndex={clickable ? 0 : undefined}
              aria-label={clickable ? `Open ${node.reference_number || node.title}` : `${node.title}, not in the library`}
              onClick={() => clickable && openNode(node)}
              onKeyDown={(ev) => {
                if (clickable && ev.key === "Enter") openNode(node);
              }}
            >
              <title>{`${node.title}${node.in_library ? "" : " (not in the library)"}`}</title>
              <rect
                width={NODE_W}
                height={NODE_H}
                rx={9}
                strokeWidth={node.is_center ? 2.5 : 1.25}
                strokeDasharray={node.in_library ? undefined : "5 4"}
                style={{ fill: style.fill, stroke: node.is_center ? "rgb(var(--accent))" : style.stroke }}
              />
              <text x={12} y={22} fontSize={13} fontWeight={700} style={{ fill: node.in_library ? "rgb(var(--ink))" : "rgb(var(--ink-3))" }}>
                {clip(node.reference_number || node.title, 25)}
              </text>
              <text x={12} y={39} fontSize={11.5} style={{ fill: "rgb(var(--ink-2))" }}>
                {style.label}
                {node.in_library && node.publication_date ? ` · ${shortDate(node.publication_date)}` : ""}
              </text>
              {node.is_center && (
                <text x={12} y={53} fontSize={10.5} fontWeight={600} style={{ fill: "rgb(var(--accent))" }}>
                  This circular
                </text>
              )}
              {node.is_private && (
                <text x={NODE_W - 10} y={53} fontSize={10.5} textAnchor="end" style={{ fill: "rgb(var(--ink-3))" }}>
                  Private
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export function GraphLegend() {
  const items: Array<[string, string]> = [
    ["IN_FORCE", "In force"],
    ["AMENDED", "Amended"],
    ["REPLACED", "Replaced"],
    ["REPEALED", "Repealed"],
  ];
  return (
    <ul className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[12.5px] text-ink-2" aria-label="Legend">
      {items.map(([k, label]) => (
        <li key={k} className="flex items-center gap-1.5">
          <span className="h-3 w-4 rounded-[3px] border" style={{ background: STATUS_STYLE[k].fill, borderColor: STATUS_STYLE[k].stroke }} />
          {label}
        </li>
      ))}
      <li className="flex items-center gap-1.5">
        <span className="h-3 w-4 rounded-[3px] border border-dashed border-line-strong bg-muted-soft" />
        Not in library
      </li>
      <li className="flex items-center gap-1.5">
        <svg width="26" height="8" aria-hidden>
          <line x1="0" y1="4" x2="26" y2="4" strokeWidth="1.6" strokeDasharray="5 4" style={{ stroke: "rgb(var(--ink-3))" }} />
        </svg>
        Awaiting review
      </li>
      <li className="flex items-center gap-1.5 text-ink-3">
        <Clock className="h-3.5 w-3.5" aria-hidden />
        Arrows point from the newer circular to the one it names
      </li>
    </ul>
  );
}
