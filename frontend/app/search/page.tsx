"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { FileSearch, Loader2, MessageSquareText, Search, X } from "lucide-react";
import {
  AUTH_CHANGED_EVENT,
  AuthUser,
  ResearchAnswer,
  SearchHit,
  SearchSnippet,
  fetchCurrentUser,
  getStoredUser,
  queryResearchAssistant,
  fetchResearchMatches,
  type ResearchCitation,
  searchCirculars,
} from "@/services/api";
import AccountModal from "@/components/AccountModal";
import StatusBadge, { PrivateTag, Tag } from "@/components/StatusBadge";
import { EmptyState, Notice, SkeletonLine, hasBangla, titleWithoutRef } from "@/components/ui";

const PAGE_SIZE = 20;
const DEBOUNCE_MS = 300;

const DEPARTMENTS = ["BRPD", "DOS", "DBI", "FEPD", "PSD", "SFD", "SMESPD"];
const DOC_TYPES = [
  { value: "CIRCULAR", label: "Circular" },
  { value: "CIRCULAR_LETTER", label: "Circular letter" },
  { value: "GUIDELINE", label: "Guideline" },
  { value: "NOTIFICATION", label: "Notification" },
  { value: "POLICY", label: "Policy" },
];
const STATUS_OPTIONS = [
  { value: "PUBLISHED", label: "Any published" },
  { value: "PUBLISHED_HUMAN_REVIEWED", label: "Signed off" },
  { value: "PUBLISHED_MACHINE_VERIFIED", label: "Machine verified" },
  { value: "AWAITING_REVIEW", label: "Awaiting review" },
];

interface Filters {
  department: string;
  year_from: string;
  year_to: string;
  doc_type: string;
  status: string;
}
const NO_FILTERS: Filters = { department: "", year_from: "", year_to: "", doc_type: "", status: "" };

type Tab = "search" | "ask";

function shortDate(value?: string) {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

function validYear(v: string) {
  return /^\d{4}$/.test(v) ? v : "";
}

/** Cuts a snippet at the match offsets (JS string indices) and wraps each match in <mark>. */
function Highlighted({ snippet }: { snippet: SearchSnippet }) {
  const { text } = snippet;
  const ranges = [...snippet.matches]
    .map(([a, b]) => [Math.max(0, a), Math.min(text.length, b)] as [number, number])
    .filter(([a, b]) => b > a)
    .sort((x, y) => x[0] - y[0]);
  const parts: React.ReactNode[] = [];
  let at = 0;
  ranges.forEach(([a, b], i) => {
    if (b <= at) return;
    const start = Math.max(a, at);
    if (start > at) parts.push(text.slice(at, start));
    parts.push(
      <mark key={i} className="rounded-[2px] bg-[rgb(var(--highlight))] px-px text-ink">
        {text.slice(start, b)}
      </mark>
    );
    at = b;
  });
  if (at < text.length) parts.push(text.slice(at));
  return (
    <span lang={hasBangla(text) ? "bn" : undefined}>
      {snippet.starts_mid_text && "… "}
      {parts}
      {snippet.ends_mid_text && " …"}
    </span>
  );
}

function openHref(documentId: string, page?: number) {
  return page ? `/?doc=${documentId}&page=${page}` : `/?doc=${documentId}`;
}

export default function SearchPage() {
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [accountOpen, setAccountOpen] = useState(false);

  const [ready, setReady] = useState(false);
  const [tab, setTab] = useState<Tab>("search");
  const [q, setQ] = useState("");
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);

  const [hits, setHits] = useState<SearchHit[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);

  const requestId = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const lastQ = useRef<string | null>(null);

  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [answer, setAnswer] = useState<ResearchAnswer | null>(null);
  const [matches, setMatches] = useState<ResearchCitation[] | null>(null);
  const [askError, setAskError] = useState<string | null>(null);
  const askId = useRef(0);

  // Signed-in user: cached copy first, then confirmed with the backend.
  useEffect(() => {
    setCurrentUser(getStoredUser());
    fetchCurrentUser()
      .then((u) => setCurrentUser(u))
      .catch(() => setCurrentUser(getStoredUser()));
    const onAuthChanged = () => setCurrentUser(getStoredUser());
    window.addEventListener(AUTH_CHANGED_EVENT, onAuthChanged);
    return () => window.removeEventListener(AUTH_CHANGED_EVENT, onAuthChanged);
  }, []);

  // Read the address bar once, so back and refresh keep the query.
  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    setQ(p.get("q") || "");
    setTab(p.get("tab") === "ask" ? "ask" : "search");
    setFilters({
      department: p.get("department") || "",
      year_from: p.get("year_from") || "",
      year_to: p.get("year_to") || "",
      doc_type: p.get("doc_type") || "",
      status: p.get("status") || "",
    });
    setReady(true);
  }, []);

  // Keep the address bar in step with the form.
  useEffect(() => {
    if (!ready) return;
    const p = new URLSearchParams();
    if (q.trim()) p.set("q", q.trim());
    (Object.keys(filters) as Array<keyof Filters>).forEach((k) => filters[k] && p.set(k, filters[k]));
    if (tab === "ask") p.set("tab", "ask");
    const qs = p.toString();
    window.history.replaceState(null, "", qs ? `/search?${qs}` : "/search");
  }, [ready, q, filters, tab]);

  const runSearch = useCallback(async (query: string, f: Filters, offset: number) => {
    const id = ++requestId.current;
    controller.current?.abort();
    const ctl = new AbortController();
    controller.current = ctl;
    if (offset === 0) setLoading(true);
    else setLoadingMore(true);
    setError(null);
    try {
      const res = await searchCirculars(
        {
          q: query,
          department: f.department,
          year_from: validYear(f.year_from),
          year_to: validYear(f.year_to),
          doc_type: f.doc_type,
          status: f.status,
          limit: PAGE_SIZE,
          offset,
        },
        ctl.signal
      );
      if (id !== requestId.current) return;
      setHits((prev) => (offset === 0 ? res.results : [...prev, ...res.results]));
      setTotal(res.total);
      setSearched(true);
    } catch (err: any) {
      if (err?.name === "AbortError" || id !== requestId.current) return;
      setError(err?.message || "Search failed.");
    } finally {
      if (id === requestId.current) {
        setLoading(false);
        setLoadingMore(false);
      }
    }
  }, []);

  const hasCriteria = !!q.trim() || Object.values(filters).some(Boolean);

  // New results when the words, the filters or the signed-in user change. Typing waits 300 ms; filters do not.
  useEffect(() => {
    if (!ready) return;
    if (!hasCriteria) {
      requestId.current++;
      controller.current?.abort();
      setHits([]);
      setTotal(0);
      setSearched(false);
      setLoading(false);
      setLoadingMore(false);
      setError(null);
      lastQ.current = q;
      return;
    }
    const typing = lastQ.current !== null && lastQ.current !== q;
    lastQ.current = q;
    const t = window.setTimeout(() => runSearch(q.trim(), filters, 0), typing ? DEBOUNCE_MS : 0);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, q, filters, currentUser?.id]);

  useEffect(() => () => controller.current?.abort(), []);

  const setFilter = (key: keyof Filters, value: string) => setFilters((f) => ({ ...f, [key]: value }));

  const ask = async (e: React.FormEvent) => {
    e.preventDefault();
    const text = question.trim();
    if (text.length < 3 || asking) return;
    const id = ++askId.current;
    setAsking(true);
    setAskError(null);
    setAnswer(null);
    setMatches(null);
    // Matching lines come from a local search and show at once; the written answer fills in after.
    fetchResearchMatches(text)
      .then((m) => {
        if (id === askId.current) setMatches(m);
      })
      .catch(() => undefined);
    try {
      const res = await queryResearchAssistant(text);
      if (id === askId.current) setAnswer(res);
    } catch (err: any) {
      if (id === askId.current) setAskError(err?.message || "Could not answer that question.");
    } finally {
      if (id === askId.current) setAsking(false);
    }
  };

  return (
    <div className="space-y-5">
      <AccountModal isOpen={accountOpen} onClose={() => setAccountOpen(false)} currentUser={currentUser} onUserChange={setCurrentUser} />

      <div>
        <h1 className="text-[26px] font-semibold tracking-[-0.015em] text-ink">Search</h1>
        <p className="mt-0.5 text-[14.5px] text-ink-3">Find words inside every circular, or ask a question and get answers with page citations.</p>
      </div>

      <div role="tablist" aria-label="Search or ask" className="inline-flex rounded-control bg-sunken p-0.5">
        {(
          [
            { id: "search", label: "Search", Icon: Search },
            { id: "ask", label: "Ask a question", Icon: MessageSquareText },
          ] as const
        ).map(({ id, label, Icon }) => (
          <button
            key={id}
            role="tab"
            type="button"
            aria-selected={tab === id}
            onClick={() => setTab(id)}
            className={`inline-flex items-center gap-1.5 rounded-[6px] px-3.5 py-1.5 text-[14px] font-semibold transition-colors ${
              tab === id ? "bg-surface text-ink shadow-sm ring-1 ring-line" : "text-ink-3 hover:text-ink"
            }`}
          >
            <Icon className="h-4 w-4" strokeWidth={1.75} />
            {label}
          </button>
        ))}
      </div>

      {tab === "search" ? (
        <section aria-label="Search circulars" className="space-y-4">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3" strokeWidth={1.75} />
            <label htmlFor="search-q" className="sr-only">
              Words to find
            </label>
            <input
              id="search-q"
              type="search"
              autoFocus
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Words, a reference number or a Bangla phrase"
              className="field h-11 pl-9 pr-9"
              lang={hasBangla(q) ? "bn" : undefined}
            />
            {q && (
              <button
                type="button"
                onClick={() => setQ("")}
                aria-label="Clear search"
                className="absolute right-2 top-1/2 grid h-7 w-7 -translate-y-1/2 place-items-center rounded text-ink-3 hover:text-ink"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <div>
              <label htmlFor="f-dept" className="field-label">
                Department
              </label>
              <select id="f-dept" className="field h-10" value={filters.department} onChange={(e) => setFilter("department", e.target.value)}>
                <option value="">All</option>
                {DEPARTMENTS.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="f-from" className="field-label">
                Year from
              </label>
              <input
                id="f-from"
                inputMode="numeric"
                maxLength={4}
                placeholder="2020"
                className="field h-10"
                value={filters.year_from}
                onChange={(e) => setFilter("year_from", e.target.value.replace(/\D/g, ""))}
              />
            </div>
            <div>
              <label htmlFor="f-to" className="field-label">
                Year to
              </label>
              <input
                id="f-to"
                inputMode="numeric"
                maxLength={4}
                placeholder="2026"
                className="field h-10"
                value={filters.year_to}
                onChange={(e) => setFilter("year_to", e.target.value.replace(/\D/g, ""))}
              />
            </div>
            <div>
              <label htmlFor="f-type" className="field-label">
                Type
              </label>
              <select id="f-type" className="field h-10" value={filters.doc_type} onChange={(e) => setFilter("doc_type", e.target.value)}>
                <option value="">All</option>
                {DOC_TYPES.map((d) => (
                  <option key={d.value} value={d.value}>
                    {d.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="f-status" className="field-label">
                Status
              </label>
              <select id="f-status" className="field h-10" value={filters.status} onChange={(e) => setFilter("status", e.target.value)}>
                <option value="">All</option>
                {STATUS_OPTIONS.map((d) => (
                  <option key={d.value} value={d.value}>
                    {d.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex items-end">
              <button type="button" className="btn-secondary h-10 w-full" disabled={!Object.values(filters).some(Boolean)} onClick={() => setFilters(NO_FILTERS)}>
                Clear filters
              </button>
            </div>
          </div>

          <div aria-live="polite" className="text-[13.5px] text-ink-3">
            {loading ? "Searching..." : searched && !error ? `${total} ${total === 1 ? "circular" : "circulars"} found` : " "}
          </div>

          {error && (
            <Notice kind="error">
              <p className="font-semibold">Search did not work</p>
              <p className="mt-0.5 text-ink-2">{error}</p>
              <button type="button" onClick={() => runSearch(q.trim(), filters, 0)} className="btn-secondary mt-2 py-1">
                Try again
              </button>
            </Notice>
          )}

          {!hasCriteria ? (
            <EmptyState title="Search every circular" icon={<FileSearch className="h-6 w-6" strokeWidth={1.5} />}>
              Type a word or phrase to find it on any page, or pick a filter to browse.
            </EmptyState>
          ) : loading && hits.length === 0 ? (
            <div className="rounded-panel border border-line bg-surface" aria-busy="true" aria-label="Searching">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="space-y-2 border-b border-line px-4 py-4 last:border-0">
                  <SkeletonLine className="h-3 w-40" />
                  <SkeletonLine className="h-3.5 w-full" />
                  <SkeletonLine className="h-3.5 w-2/3" />
                </div>
              ))}
            </div>
          ) : searched && !error && hits.length === 0 ? (
            <EmptyState title="Nothing found" icon={<Search className="h-6 w-6" strokeWidth={1.5} />}>
              No circular matches. Try fewer or different words, or clear a filter.
            </EmptyState>
          ) : (
            hits.length > 0 && (
              <>
                <ul className={`overflow-hidden rounded-panel border border-line bg-surface transition-opacity ${loading ? "opacity-60" : ""}`}>
                  {hits.map((hit) => (
                    <li key={hit.document_id} className="border-b border-line px-4 py-4 last:border-0">
                      <Link href={openHref(hit.document_id)} className="group block">
                        <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                          <span className="refno">{hit.reference_number || "Circular"}</span>
                          {hit.is_private && <PrivateTag />}
                          <StatusBadge status={hit.publication_status} size="sm" />
                          {hit.title_match && <Tag tone="accent">Title match</Tag>}
                          <span className="ml-auto text-[12.5px] tabular-nums text-ink-3">{shortDate(hit.publication_date)}</span>
                        </span>
                        <span className="mt-1.5 block text-[15.5px] font-semibold leading-snug text-ink group-hover:text-accent">
                          {titleWithoutRef(hit.title, hit.reference_number)}
                        </span>
                        {hit.title_bn && (
                          <span lang="bn" className="mt-0.5 block text-[14.5px] leading-snug text-ink-2">
                            {hit.title_bn}
                          </span>
                        )}
                      </Link>
                      <p className="mt-1 text-[12.5px] text-ink-3">
                        {hit.matching_pages > 0 ? `${hit.matching_pages} matching ${hit.matching_pages === 1 ? "page" : "pages"}` : "No page text matched"}
                      </p>
                      {hit.snippets.length > 0 && (
                        <ul className="mt-2 space-y-2">
                          {hit.snippets.map((s, i) => (
                            <li key={`${s.version_id}-${s.page_number}-${i}`}>
                              <Link
                                href={openHref(hit.document_id, s.page_number)}
                                className="block rounded-control border border-line bg-sunken/50 px-3 py-2 text-[14px] leading-[1.65] text-ink-2 transition-colors hover:border-accent/50 hover:bg-accent-soft"
                              >
                                <span className="mb-0.5 block text-[12px] font-semibold text-ink-3">Page {s.page_number}</span>
                                <span className="break-words">
                                  <Highlighted snippet={s} />
                                </span>
                              </Link>
                            </li>
                          ))}
                        </ul>
                      )}
                    </li>
                  ))}
                </ul>
                {hits.length < total && (
                  <div className="flex justify-center">
                    <button type="button" onClick={() => runSearch(q.trim(), filters, hits.length)} disabled={loadingMore || loading} className="btn-secondary">
                      {loadingMore ? (
                        <>
                          <Loader2 className="h-4 w-4 animate-spin" /> Loading...
                        </>
                      ) : (
                        `Load more (${total - hits.length} left)`
                      )}
                    </button>
                  </div>
                )}
              </>
            )
          )}
        </section>
      ) : (
        <section aria-label="Ask a question" className="space-y-4">
          {!currentUser ? (
            <EmptyState title="Sign in to ask" icon={<MessageSquareText className="h-6 w-6" strokeWidth={1.5} />}>
              Questions are answered from the circulars you can read, with the exact page quoted.
              <div className="mt-3">
                <button type="button" onClick={() => setAccountOpen(true)} className="btn-primary">
                  Sign in to ask
                </button>
              </div>
            </EmptyState>
          ) : (
            <form onSubmit={ask} className="space-y-3">
              <div>
                <label htmlFor="ask-q" className="field-label">
                  Your question
                </label>
                <textarea
                  id="ask-q"
                  rows={3}
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  disabled={asking}
                  placeholder="For example: What is the cash reserve ratio for scheduled banks?"
                  lang={hasBangla(question) ? "bn" : undefined}
                  className="field resize-y text-[15px] leading-relaxed"
                />
              </div>
              <button type="submit" disabled={asking || question.trim().length < 3} className="btn-primary">
                {asking ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" /> Looking through the circulars...
                  </>
                ) : (
                  "Ask"
                )}
              </button>
            </form>
          )}

          {askError && <Notice kind="error">{askError}</Notice>}

          {asking && !answer && (
            <div className="space-y-3" aria-live="polite">
              <p className="flex items-center gap-2 text-[14px] text-ink-2">
                <Loader2 className="h-4 w-4 animate-spin" /> Writing the answer. Matching lines are below already.
              </p>
              {matches && matches.length > 0 && (
                <ul className="space-y-2">
                  {matches.map((c, i) => (
                    <li key={`m-${c.document_id}-${c.page_number}-${i}`}>
                      <Link
                        href={openHref(c.document_id || "", c.page_number)}
                        className="block rounded-panel border border-line bg-surface px-3.5 py-3 transition-colors hover:border-accent/50 hover:bg-accent-soft"
                      >
                        <span className="flex flex-wrap items-baseline gap-x-2">
                          <span className="refno">{c.reference_number || c.document_title}</span>
                          <span className="text-[12.5px] font-semibold text-ink-3">Page {c.page_number}</span>
                        </span>
                        <blockquote
                          lang={hasBangla(c.verbatim_excerpt) ? "bn" : undefined}
                          className="mt-1 whitespace-pre-wrap break-words border-l-2 border-line pl-3 text-[14px] leading-[1.65] text-ink-2"
                        >
                          {c.verbatim_excerpt}
                        </blockquote>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
              {matches && matches.length === 0 && (
                <p className="text-[13.5px] text-ink-3">No line uses those exact words. The answer may still find it.</p>
              )}
            </div>
          )}

          {answer && (
            <div className="space-y-3" aria-live="polite">
              {!answer.is_grounded && <Notice kind="warning">Could not verify this from the circulars. Nothing below is confirmed by a source page.</Notice>}
              <div className="rounded-panel border border-line bg-surface p-4">
                <h2 className="text-[13px] font-semibold uppercase tracking-wide text-ink-3">Answer</h2>
                <p lang={hasBangla(answer.answer) ? "bn" : undefined} className="mt-1.5 whitespace-pre-wrap break-words text-[15.5px] leading-[1.7] text-ink">
                  {answer.answer}
                </p>
              </div>

              {answer.caveats.length > 0 && (
                <Notice kind="info">
                  <p className="font-semibold">Keep in mind</p>
                  <ul className="mt-1 list-disc space-y-0.5 pl-4 text-ink-2">
                    {answer.caveats.map((c, i) => (
                      <li key={i}>{c}</li>
                    ))}
                  </ul>
                </Notice>
              )}

              {answer.citations.length > 0 && (
                <div>
                  <h2 className="mb-2 text-[13px] font-semibold uppercase tracking-wide text-ink-3">Sources</h2>
                  <ul className="space-y-2">
                    {answer.citations.map((c, i) => {
                      const body = (
                        <>
                          <span className="flex flex-wrap items-baseline gap-x-2">
                            <span className="refno">{c.reference_number || c.document_title}</span>
                            <span className="text-[12.5px] font-semibold text-ink-3">Page {c.page_number}</span>
                          </span>
                          <blockquote
                            lang={hasBangla(c.verbatim_excerpt) ? "bn" : undefined}
                            className="mt-1 whitespace-pre-wrap break-words border-l-2 border-accent/50 pl-3 text-[14px] leading-[1.65] text-ink-2"
                          >
                            {c.verbatim_excerpt}
                          </blockquote>
                        </>
                      );
                      return (
                        <li key={`${c.document_id}-${c.page_number}-${i}`}>
                          {c.document_id ? (
                            <Link
                              href={openHref(c.document_id, c.page_number)}
                              className="block rounded-panel border border-line bg-surface px-3.5 py-3 transition-colors hover:border-accent/50 hover:bg-accent-soft"
                            >
                              {body}
                            </Link>
                          ) : (
                            <div className="rounded-panel border border-line bg-surface px-3.5 py-3">{body}</div>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
