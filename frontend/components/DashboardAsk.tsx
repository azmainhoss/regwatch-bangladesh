"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { ArrowUp, Loader2, X } from "lucide-react";
import { fetchResearchMatches, queryResearchAssistant, type ResearchAnswer, type ResearchCitation, openRegister } from "@/services/api";
import { Notice } from "@/components/ui";

const hasBangla = (s?: string | null) => !!s && /[ঀ-৿]/.test(s);
const openHref = (docId: string, page: number) => `/dashboard?doc=${docId}&page=${page}`;

function Source({ c, strong }: { c: ResearchCitation; strong?: boolean }) {
  const body = (
    <>
      <span className="flex flex-wrap items-baseline gap-x-2">
        <span className="refno">{c.reference_number || c.document_title}</span>
        <span className="text-[12.5px] font-semibold text-ink-3">Page {c.page_number}</span>
      </span>
      <blockquote
        lang={hasBangla(c.verbatim_excerpt) ? "bn" : undefined}
        className={`mt-1 line-clamp-4 whitespace-pre-wrap break-words border-l-2 pl-3 text-[13.5px] leading-[1.6] text-ink-2 ${strong ? "border-accent/50" : "border-line"}`}
      >
        {c.verbatim_excerpt}
      </blockquote>
    </>
  );
  return c.document_id ? (
    <Link href={openHref(c.document_id, c.page_number)} className="block rounded-panel border border-line bg-surface px-3 py-2.5 transition-colors hover:border-accent/50 hover:bg-accent-soft">
      {body}
    </Link>
  ) : (
    <div className="rounded-panel border border-line bg-surface px-3 py-2.5">{body}</div>
  );
}

const QUESTION_START =
  /^(what|whats|what's|how|when|where|which|who|whom|whose|why|is|are|was|were|does|do|did|can|could|should|shall|will|would|may|must|has|have|explain|tell|list|give|show me|compare)\b/i;
const BANGLA_QUESTION = /(কি|কী|কেন|কীভাবে|কিভাবে|কখন|কোথায়|কোন|কত|কে|কারা)/;

/** A question goes to Ask; anything else filters the circular list (owner, 2026-11-26: one box, auto-detect). */
export function isQuestion(text: string): boolean {
  const t = text.trim();
  if (t.length < 3) return false;
  return t.endsWith("?") || t.endsWith("？") || QUESTION_START.test(t) || BANGLA_QUESTION.test(t);
}

/**
 * One box for search and Ask. Typing that is not a question filters the list as you type (onSearch); a question
 * (ends with "?" or starts with what / how / when / ...) is sent to Ask with Enter or the arrow button. On the home
 * page (no list) a plain search opens the dashboard with it.
 */
export default function DashboardAsk({
  signedIn,
  onSearch,
  initial = "",
  inputId = "dash-ask",
}: {
  signedIn: boolean;
  onSignIn?: () => void;
  /** Live search of the list. Without it (home page), Enter on a plain search opens the dashboard. */
  onSearch?: (text: string) => void;
  initial?: string;
  inputId?: string;
}) {
  const [q, setQ] = useState(initial);
  const [asking, setAsking] = useState(false);
  const [answer, setAnswer] = useState<ResearchAnswer | null>(null);
  const [matches, setMatches] = useState<ResearchCitation[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const id = useRef(0);
  const question = isQuestion(q);

  const change = (text: string) => {
    setQ(text);
    // A question does not filter the list (it would match almost nothing); plain words do, as you type.
    if (onSearch) onSearch(isQuestion(text) ? "" : text);
  };

  const ask = async (e?: React.FormEvent) => {
    e?.preventDefault();
    const text = q.trim();
    if (!question) {
      if (!onSearch && text) window.location.href = `/dashboard?q=${encodeURIComponent(text)}`;
      return;
    }
    if (!signedIn) return openRegister("register");
    if (text.length < 3 || asking) return;
    const mine = ++id.current;
    setAsking(true);
    setError(null);
    setAnswer(null);
    setMatches(null);
    fetchResearchMatches(text)
      .then((m) => mine === id.current && setMatches(m))
      .catch(() => undefined);
    try {
      const res = await queryResearchAssistant(text);
      if (mine === id.current) setAnswer(res);
    } catch (err: any) {
      if (mine === id.current) setError(err?.message || "Could not answer that question.");
    } finally {
      if (mine === id.current) setAsking(false);
    }
  };

  const clear = () => {
    id.current++;
    setAnswer(null);
    setMatches(null);
    setError(null);
    setAsking(false);
  };

  const shown = answer || (asking && matches) || error;

  return (
    <section aria-label="Search or ask" className="mx-auto w-full max-w-[760px]">
      <form onSubmit={ask} className="relative rounded-[20px] border border-line-strong bg-surface shadow-panel transition-colors focus-within:border-accent">
        <label htmlFor={inputId} className="sr-only">
          Search circulars or ask a question
        </label>
        <textarea
          id={inputId}
          value={q}
          rows={2}
          onChange={(e) => change(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void ask();
            }
          }}
          placeholder="Search circulars, or ask a question (e.g. What is the SMA loan provision rate?)"
          lang={hasBangla(q) ? "bn" : undefined}
          className="block min-h-[96px] w-full resize-none rounded-[20px] bg-transparent px-5 pb-12 pt-4 text-[16px] leading-relaxed text-ink placeholder:text-ink-3 focus:outline-none"
        />
        <div className="pointer-events-none absolute inset-x-4 bottom-3 flex items-center justify-between gap-3">
          <span className="truncate text-[12.5px] text-ink-3">
            {q.trim() ? (question ? (signedIn ? "Question: press Enter to ask" : "Question: register free to ask") : "Searching the circulars as you type") : ""}
          </span>
          <span className="pointer-events-auto flex items-center gap-2">
            {q && (
              <button type="button" onClick={() => { change(""); clear(); }} aria-label="Clear" className="grid h-8 w-8 place-items-center rounded-full text-ink-3 hover:bg-sunken hover:text-ink">
                <X className="h-4 w-4" />
              </button>
            )}
            <button
              type="submit"
              disabled={asking || !q.trim() || (!question && !!onSearch)}
              aria-label={question ? "Ask" : "Search"}
              className="grid h-10 w-10 place-items-center rounded-full bg-accent text-accent-ink transition-colors hover:bg-accent-hover disabled:opacity-40"
            >
              {asking ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowUp className="h-5 w-5" strokeWidth={2.25} />}
            </button>
          </span>
        </div>
      </form>

      {shown && (
        <div className="mt-3 space-y-2.5 rounded-[14px] border border-line bg-surface p-4" aria-live="polite">
          <div className="flex items-center justify-between">
            <p className="text-[12.5px] font-semibold uppercase tracking-wide text-ink-3">{answer ? "Answer" : asking ? "Matching lines while the answer is written" : ""}</p>
            <button type="button" onClick={clear} className="grid h-7 w-7 place-items-center rounded-control text-ink-3 hover:bg-sunken hover:text-ink" aria-label="Close the answer">
              <X className="h-4 w-4" />
            </button>
          </div>
          {error && <Notice kind="error">{error}</Notice>}
          {answer && (
            <>
              {!answer.is_grounded && <Notice kind="warning">Could not confirm this from the circulars. Nothing below is backed by a source page.</Notice>}
              <p lang={hasBangla(answer.answer) ? "bn" : undefined} className="whitespace-pre-wrap break-words text-[15px] leading-[1.7] text-ink">
                {answer.answer}
              </p>
              {answer.citations.length > 0 && (
                <ul className="grid gap-2 md:grid-cols-2">
                  {answer.citations.slice(0, 6).map((c, i) => (
                    <li key={`${c.document_id}-${c.page_number}-${i}`}>
                      <Source c={c} strong />
                    </li>
                  ))}
                </ul>
              )}
              <Link href={`/search?tab=ask&q=${encodeURIComponent(q.trim())}`} className="inline-block text-[13.5px] font-semibold text-accent hover:underline">
                Open in Search for more
              </Link>
            </>
          )}
          {!answer && asking && matches && matches.length > 0 && (
            <ul className="grid gap-2 md:grid-cols-2">
              {matches.slice(0, 4).map((c, i) => (
                <li key={`m-${c.document_id}-${c.page_number}-${i}`}>
                  <Source c={c} />
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
