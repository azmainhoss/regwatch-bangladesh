"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { Loader2, MessageSquareText, X } from "lucide-react";
import { fetchResearchMatches, queryResearchAssistant, type ResearchAnswer, type ResearchCitation } from "@/services/api";
import { Notice } from "@/components/ui";

const hasBangla = (s?: string | null) => !!s && /[ঀ-৿]/.test(s);
const openHref = (docId: string, page: number) => `/?doc=${docId}&page=${page}`;

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

/** "Ask a question" on the home screen: answers from every circular, each point tied to its page. */
export default function DashboardAsk({ signedIn, onSignIn }: { signedIn: boolean; onSignIn: () => void }) {
  const [q, setQ] = useState("");
  const [asking, setAsking] = useState(false);
  const [answer, setAnswer] = useState<ResearchAnswer | null>(null);
  const [matches, setMatches] = useState<ResearchCitation[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const id = useRef(0);

  const ask = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!signedIn) return onSignIn();
    const text = q.trim();
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
    <section aria-label="Ask a question" className="rounded-panel border border-line bg-surface p-3.5 sm:p-4">
      <form onSubmit={ask} className="flex flex-col gap-2 sm:flex-row">
        <label htmlFor="dash-ask" className="sr-only">
          Ask a question about the circulars
        </label>
        <div className="relative flex-1">
          <MessageSquareText className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3" strokeWidth={1.75} />
          <input
            id="dash-ask"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Ask a question, e.g. What is the provision rate for SMA loans?"
            lang={hasBangla(q) ? "bn" : undefined}
            className="field h-11 pl-9 text-[15px]"
          />
        </div>
        <button type="submit" disabled={asking || (signedIn && q.trim().length < 3)} className="btn-primary h-11 px-5">
          {asking ? <Loader2 className="h-4 w-4 animate-spin" /> : signedIn ? "Ask" : "Sign in to ask"}
        </button>
      </form>

      {shown && (
        <div className="mt-3 space-y-2.5" aria-live="polite">
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
