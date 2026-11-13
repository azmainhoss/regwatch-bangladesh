"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, ArrowLeftRight, ChevronDown, GitCompareArrows, Search } from "lucide-react";
import {
  CompareOp,
  CompareResult,
  CompareSide,
  DocumentItem,
  compareVersions,
  fetchDocument,
  fetchDocuments,
} from "@/services/api";
import { loadStatus, useRelState } from "@/services/relationshipsStore";
import { EmptyState, Notice, SkeletonLine, hasBangla } from "@/components/ui";

// ------------------------------------------------------------------------------------ picker

interface VersionOption {
  versionId: string;
  docId: string;
  reference: string;
  title: string;
  versionNumber: number;
  language: string;
  pages: number;
  isCurrent: boolean;
  group: "suggested" | "search";
}

const LANGUAGE: Record<string, string> = { en: "English", bn: "Bangla", mixed: "English and Bangla" };

function optionsFor(doc: DocumentItem, group: VersionOption["group"]): VersionOption[] {
  return [...(doc.versions ?? [])]
    .sort((a, b) => b.version_number - a.version_number)
    .map((v) => ({
      versionId: v.id,
      docId: doc.id,
      reference: doc.reference_number || "Circular",
      title: doc.title,
      versionNumber: v.version_number,
      language: v.language,
      pages: v.page_count,
      isCurrent: v.id === doc.current_version_id,
      group,
    }));
}

function sideLabel(side?: CompareSide | null) {
  if (!side) return null;
  return `${side.reference_number || "Circular"} · version ${side.version_number} · ${LANGUAGE[side.language] ?? side.language}`;
}

function VersionPicker({
  label,
  side,
  suggestions,
  onPick,
  testId,
}: {
  label: string;
  side?: CompareSide | null;
  suggestions: VersionOption[];
  onPick: (versionId: string) => void;
  testId: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [found, setFound] = useState<VersionOption[]>([]);
  const [searching, setSearching] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!boxRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    let alive = true;
    setSearching(true);
    const t = window.setTimeout(
      () => {
        fetchDocuments({ search: query.trim() || undefined, corpus_type: "GENUINE" })
          .then((docs) => alive && setFound(docs.flatMap((d) => optionsFor(d, "search"))))
          .catch(() => alive && setFound([]))
          .finally(() => alive && setSearching(false));
      },
      query ? 250 : 0
    );
    return () => {
      alive = false;
      window.clearTimeout(t);
    };
  }, [open, query]);

  const row = (o: VersionOption) => (
    <li key={`${o.group}-${o.versionId}`}>
      <button
        type="button"
        onClick={() => {
          onPick(o.versionId);
          setOpen(false);
        }}
        className="block w-full px-3 py-2 text-left hover:bg-sunken"
        data-testid="picker-option"
      >
        <span className="flex flex-wrap items-center gap-x-2 text-[13.5px]">
          <span className="refno">{o.reference}</span>
          <span className="text-ink-3">
            version {o.versionNumber} &middot; {LANGUAGE[o.language] ?? o.language} &middot; {o.pages} {o.pages === 1 ? "page" : "pages"}
            {o.isCurrent ? " · current" : ""}
          </span>
        </span>
        <span className="mt-0.5 line-clamp-1 block text-[13px] text-ink-2">{o.title}</span>
      </button>
    </li>
  );

  return (
    <div ref={boxRef} className="relative min-w-0">
      <p className="field-label">{label}</p>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="listbox"
        data-testid={testId}
        className="field flex h-auto min-h-[2.5rem] items-center justify-between gap-2 text-left"
      >
        <span className="min-w-0">
          {side ? (
            <>
              <span className="block truncate font-semibold text-ink">{sideLabel(side)}</span>
              <span className="block truncate text-[12.5px] text-ink-3">{side.title}</span>
            </>
          ) : (
            <span className="text-ink-3">Choose a circular and version</span>
          )}
        </span>
        <ChevronDown className="h-4 w-4 shrink-0 text-ink-3" aria-hidden />
      </button>
      {open && (
        <div className="absolute left-0 right-0 z-30 mt-1 overflow-hidden rounded-panel border border-line bg-surface shadow-pop">
          <div className="relative border-b border-line p-2">
            <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3" aria-hidden />
            <input
              autoFocus
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by number or title"
              aria-label="Search circulars"
              className="field h-9 pl-8"
            />
          </div>
          <ul role="listbox" className="max-h-72 overflow-y-auto py-1">
            {!query && suggestions.length > 0 && (
              <>
                <li className="px-3 pb-1 pt-2 text-[12px] font-semibold uppercase tracking-wide text-ink-3">Linked to this circular</li>
                {suggestions.map(row)}
                <li className="px-3 pb-1 pt-2 text-[12px] font-semibold uppercase tracking-wide text-ink-3">All circulars</li>
              </>
            )}
            {found.map(row)}
            {!searching && found.length === 0 && <li className="px-3 py-3 text-[13.5px] text-ink-3">Nothing found.</li>}
            {searching && found.length === 0 && <li className="px-3 py-3 text-[13.5px] text-ink-3">Searching...</li>}
          </ul>
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------------------------ diff

function PageTag({ side, page }: { side: CompareSide; page?: number | null }) {
  if (!page) return null;
  return (
    <Link
      href={`/?doc=${side.document_id}&page=${page}`}
      className="shrink-0 rounded-control px-1.5 py-px text-[12px] font-semibold text-accent ring-1 ring-inset ring-accent/25 hover:bg-accent-soft"
      title={`Open page ${page} of ${side.reference_number || "the circular"}`}
    >
      p. {page}
    </Link>
  );
}

function Words({ op, side }: { op: CompareOp; side: "left" | "right" | "both" }) {
  return (
    <>
      {op.words.map((w, i) => {
        if (w.op === "equal") return <span key={i}>{w.text}</span>;
        if (w.op === "delete" && side !== "right")
          return (
            <del key={i} className="rounded-[3px] bg-bad-soft text-bad line-through decoration-bad/70" data-testid="word-deleted">
              {w.text}
            </del>
          );
        if (w.op === "insert" && side !== "left")
          return (
            <ins key={i} className="rounded-[3px] bg-ok-soft text-ok no-underline" data-testid="word-inserted">
              {w.text}
            </ins>
          );
        return null;
      })}
    </>
  );
}

function plainText(text?: string | null) {
  return (
    <p className="text-[14.5px] leading-relaxed text-ink" lang={hasBangla(text) ? "bn" : undefined}>
      {text}
    </p>
  );
}

type Block = { kind: "equal"; ops: CompareOp[]; index: number } | { kind: "change"; op: CompareOp };

function toBlocks(ops: CompareOp[]): Block[] {
  const blocks: Block[] = [];
  let run: CompareOp[] = [];
  const flush = () => {
    if (run.length) blocks.push({ kind: "equal", ops: run, index: blocks.length });
    run = [];
  };
  for (const op of ops) {
    if (op.op === "equal") run.push(op);
    else {
      flush();
      blocks.push({ kind: "change", op });
    }
  }
  flush();
  return blocks;
}

function ChangeRow({ op, left, right }: { op: CompareOp; left: CompareSide; right: CompareSide }) {
  const empty = <div aria-hidden className="rounded-panel border border-dashed border-line bg-sunken/30" />;
  return (
    <>
      {/* Wide screens: old on the left, new on the right. */}
      <div className="hidden gap-4 lg:grid lg:grid-cols-2" data-testid="diff-row" data-op={op.op}>
        {op.op === "insert" ? (
          empty
        ) : (
          <div className="space-y-1.5 rounded-panel border border-line bg-surface px-3.5 py-3">
            <div className="flex justify-end">
              <PageTag side={left} page={op.left_page} />
            </div>
            <p className="text-[14.5px] leading-relaxed text-ink" lang={hasBangla(op.left_text) ? "bn" : undefined}>
              {op.op === "delete" ? (
                <del className="rounded-[3px] bg-bad-soft text-bad line-through decoration-bad/70" data-testid="word-deleted">
                  {op.left_text}
                </del>
              ) : (
                <Words op={op} side="left" />
              )}
            </p>
          </div>
        )}
        {op.op === "delete" ? (
          empty
        ) : (
          <div className="space-y-1.5 rounded-panel border border-line bg-surface px-3.5 py-3">
            <div className="flex justify-end">
              <PageTag side={right} page={op.right_page} />
            </div>
            <p className="text-[14.5px] leading-relaxed text-ink" lang={hasBangla(op.right_text) ? "bn" : undefined}>
              {op.op === "insert" ? (
                <ins className="rounded-[3px] bg-ok-soft text-ok no-underline" data-testid="word-inserted">
                  {op.right_text}
                </ins>
              ) : (
                <Words op={op} side="right" />
              )}
            </p>
          </div>
        )}
      </div>

      {/* Phone and tablet: one stacked block with the changes marked inside the text. */}
      <div className="space-y-1.5 rounded-panel border border-line bg-surface px-3.5 py-3 lg:hidden" data-testid="diff-row-stacked" data-op={op.op}>
        <div className="flex items-center justify-between gap-2 text-[12px] font-semibold text-ink-3">
          <span>{op.op === "insert" ? "Added" : op.op === "delete" ? "Removed" : "Changed"}</span>
          <span className="flex items-center gap-1.5">
            {op.op !== "insert" && <PageTag side={left} page={op.left_page} />}
            {op.op === "replace" && <span aria-hidden>&rarr;</span>}
            {op.op !== "delete" && <PageTag side={right} page={op.right_page} />}
          </span>
        </div>
        <p className="text-[14.5px] leading-relaxed text-ink" lang={hasBangla(op.right_text ?? op.left_text) ? "bn" : undefined}>
          <Words op={op} side="both" />
        </p>
      </div>
    </>
  );
}

function EqualRun({ block, left, right }: { block: Extract<Block, { kind: "equal" }>; left: CompareSide; right: CompareSide }) {
  const [open, setOpen] = useState(false);
  const n = block.ops.length;
  return (
    <div className="space-y-3" data-testid="equal-run">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-center gap-1.5 rounded-control border border-dashed border-line-strong px-3 py-1.5 text-[13px] font-semibold text-ink-3 hover:bg-sunken hover:text-ink-2"
      >
        <ChevronDown className={`h-3.5 w-3.5 transition-transform ${open ? "rotate-180" : ""}`} aria-hidden />
        {open ? `Hide ${n} unchanged ${n === 1 ? "paragraph" : "paragraphs"}` : `${n} unchanged ${n === 1 ? "paragraph" : "paragraphs"}`}
      </button>
      {open &&
        block.ops.map((op, i) => (
          <div key={i}>
            <div className="hidden gap-4 lg:grid lg:grid-cols-2">
              <div className="rounded-panel bg-sunken/50 px-3.5 py-2.5">
                <div className="flex justify-end">
                  <PageTag side={left} page={op.left_page} />
                </div>
                {plainText(op.left_text)}
              </div>
              <div className="rounded-panel bg-sunken/50 px-3.5 py-2.5">
                <div className="flex justify-end">
                  <PageTag side={right} page={op.right_page} />
                </div>
                {plainText(op.right_text)}
              </div>
            </div>
            <div className="rounded-panel bg-sunken/50 px-3.5 py-2.5 lg:hidden">
              <div className="flex justify-end">
                <PageTag side={right} page={op.right_page} />
              </div>
              {plainText(op.right_text)}
            </div>
          </div>
        ))}
    </div>
  );
}

// ------------------------------------------------------------------------------------ page

function ComparePageInner() {
  const router = useRouter();
  const search = useSearchParams();
  const left = search.get("left") || "";
  const right = search.get("right") || "";
  const docParam = search.get("doc") || "";

  const [result, setResult] = useState<CompareResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<VersionOption[]>([]);
  const rel = useRelState();

  const setSides = useCallback(
    (nextLeft: string, nextRight: string) => {
      const p = new URLSearchParams();
      if (nextLeft) p.set("left", nextLeft);
      if (nextRight) p.set("right", nextRight);
      if (docParam) p.set("doc", docParam);
      router.replace(`/compare?${p.toString()}`, { scroll: false });
    },
    [router, docParam]
  );

  // Fetch the comparison whenever both files are chosen.
  useEffect(() => {
    if (!left || !right) {
      setResult(null);
      setError(null);
      return;
    }
    const ctrl = new AbortController();
    setLoading(true);
    setError(null);
    compareVersions(left, right, ctrl.signal)
      .then((r) => {
        if (ctrl.signal.aborted) return;
        setResult(r);
        setError(null);
        setLoading(false);
      })
      .catch((e: any) => {
        // A request replaced by a newer one (or by leaving the page) is not an error.
        if (ctrl.signal.aborted || e?.name === "AbortError") return;
        setResult(null);
        setError(e.message || "Could not compare these files.");
        setLoading(false);
      });
    return () => ctrl.abort();
  }, [left, right]);

  // Suggestions: this circular's own files and the files of the circulars linked to it.
  useEffect(() => {
    const anchor = docParam || result?.right.document_id;
    if (!anchor) return;
    loadStatus(anchor).catch(() => undefined);
  }, [docParam, result?.right.document_id]);

  const anchorId = docParam || result?.right.document_id || "";
  const anchorStatus = anchorId ? rel.status[anchorId] : undefined;
  useEffect(() => {
    if (!anchorId) return;
    let alive = true;
    const ids = new Set<string>([anchorId]);
    anchorStatus?.outgoing.forEach((l) => l.target && ids.add(l.target.id));
    anchorStatus?.verified_incoming.forEach((l) => ids.add(l.source.id));
    Promise.all(Array.from(ids).map((id) => fetchDocument(id).catch(() => null))).then((docs) => {
      if (!alive) return;
      setSuggestions(docs.filter((d): d is DocumentItem => !!d).flatMap((d) => optionsFor(d, "suggested")));
    });
    return () => {
      alive = false;
    };
  }, [anchorId, anchorStatus?.outgoing.length, anchorStatus?.verified_incoming.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const blocks = useMemo(() => (result ? toBlocks(result.ops) : []), [result]);
  const changed = result ? result.stats.insert + result.stats.delete + result.stats.replace : 0;

  return (
    <div className="space-y-5">
      <div>
        <Link href={docParam ? `/?doc=${docParam}` : "/"} className="btn-ghost -ml-2">
          <ArrowLeft className="h-4 w-4" strokeWidth={1.75} />
          Back
        </Link>
      </div>

      <div>
        <h1 className="flex items-center gap-2 text-[26px] font-semibold tracking-[-0.015em] text-ink">
          <GitCompareArrows className="h-6 w-6 text-ink-3" strokeWidth={1.5} aria-hidden />
          Compare circulars
        </h1>
        <p className="mt-0.5 text-[14.5px] text-ink-3">The older text on the left, the newer on the right. Added words are green, removed words are red and struck through.</p>
      </div>

      <div className="grid grid-cols-1 items-end gap-3 md:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]">
        <VersionPicker label="Older (left)" side={result?.left} suggestions={suggestions} onPick={(v) => setSides(v, right)} testId="picker-left" />
        <button
          type="button"
          onClick={() => setSides(right, left)}
          disabled={!left || !right}
          className="btn-secondary h-10 justify-self-start md:justify-self-auto"
          aria-label="Swap the two sides"
        >
          <ArrowLeftRight className="h-4 w-4" strokeWidth={1.75} />
          <span className="md:sr-only">Swap sides</span>
        </button>
        <VersionPicker label="Newer (right)" side={result?.right} suggestions={suggestions} onPick={(v) => setSides(left, v)} testId="picker-right" />
      </div>

      {!left || !right ? (
        <EmptyState title="Pick two files to compare" icon={<GitCompareArrows className="h-6 w-6" strokeWidth={1.5} />}>
          Choose an older and a newer circular above. From a circular&rsquo;s page you can also use &ldquo;Compare with the circular it replaces&rdquo;.
        </EmptyState>
      ) : error ? (
        <Notice kind="error">{error}</Notice>
      ) : loading && !result ? (
        <div className="space-y-3" aria-busy="true" aria-label="Comparing">
          <SkeletonLine className="h-5 w-64" />
          <SkeletonLine className="h-20 w-full" />
          <SkeletonLine className="h-20 w-full" />
        </div>
      ) : result ? (
        <div className={`space-y-4 transition-opacity ${loading ? "opacity-60" : ""}`}>
          <p className="text-[14px] text-ink-2" data-testid="compare-summary">
            {changed === 0 ? (
              <span className="font-semibold text-ok">The text is the same in both files.</span>
            ) : (
              <>
                <span className="font-semibold text-ink">{result.stats.replace}</span> changed &middot; <span className="font-semibold text-ok">{result.stats.insert}</span> added &middot;{" "}
                <span className="font-semibold text-bad">{result.stats.delete}</span> removed &middot; <span className="font-semibold text-ink">{result.stats.equal}</span> unchanged
              </>
            )}
          </p>
          {result.truncated && (
            <Notice kind="warning">
              These files are long, so only the first {Math.max(result.left.pages_compared, result.right.pages_compared)} pages of each were compared.
            </Notice>
          )}
          <div className="sticky top-14 z-20 hidden gap-4 border-b border-line bg-canvas/95 py-2 backdrop-blur lg:grid lg:grid-cols-2">
            <p className="truncate text-[13px] font-semibold text-ink-2">{sideLabel(result.left)}</p>
            <p className="truncate text-[13px] font-semibold text-ink-2">{sideLabel(result.right)}</p>
          </div>
          <div className="space-y-3" data-testid="diff">
            {blocks.length === 0 && <EmptyState title="No text to compare">Neither file has page text yet.</EmptyState>}
            {blocks.map((b, i) =>
              b.kind === "equal" ? (
                <EqualRun key={i} block={b} left={result.left} right={result.right} />
              ) : (
                <ChangeRow key={i} op={b.op} left={result.left} right={result.right} />
              )
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default function ComparePage() {
  return (
    <Suspense fallback={<SkeletonLine className="h-8 w-64" />}>
      <ComparePageInner />
    </Suspense>
  );
}
