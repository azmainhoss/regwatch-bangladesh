"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Search } from "lucide-react";
import { fetchFeed } from "@/services/libraryApi";
import type { DocumentItem } from "@/services/api";
import { titleWithoutRef } from "@/components/ui";

/** Any address that does not exist: say so plainly, offer a search and the newest circulars. */
export default function NotFound() {
  const [recent, setRecent] = useState<DocumentItem[] | null>(null);

  useEffect(() => {
    fetchFeed({ period: null, saved: null, department: null, topic: null, q: "", limit: 5, offset: 0 })
      .then((p) => setRecent(p.items))
      .catch(() => setRecent([]));
  }, []);

  return (
    <div className="mx-auto max-w-[640px] py-10 sm:py-16">
      <p className="text-[13px] font-semibold uppercase tracking-wide text-ink-3">404</p>
      <h1 className="mt-1 font-serif text-[36px] font-medium leading-tight text-ink sm:text-[44px]">This page isn’t here</h1>
      <p className="mt-3 text-[16px] leading-relaxed text-ink-2">
        The link may be old or mistyped. Search the circulars, or open one of the newest below.
      </p>

      <form action="/search" method="get" className="mt-6 flex gap-2" role="search">
        <label htmlFor="nf-q" className="sr-only">
          Search circulars
        </label>
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3" strokeWidth={1.75} />
          <input id="nf-q" name="q" placeholder="e.g. BRPD 40, SMA loans" className="field h-12 rounded-[10px] pl-9 text-[16px]" />
        </div>
        <button type="submit" className="btn-primary h-12 rounded-[10px] px-6 text-[16px] font-bold">
          Search
        </button>
      </form>

      <h2 className="mt-10 text-[15px] font-bold text-ink">Newest circulars</h2>
      <ul className="mt-3 divide-y divide-line rounded-[14px] border border-line bg-surface">
        {(recent ?? Array.from({ length: 5 }, () => null)).map((d, i) => (
          <li key={d?.id ?? i}>
            {d ? (
              <Link href={`/dashboard?doc=${d.id}`} className="block px-4 py-3 hover:bg-sunken">
                <span className="block text-[13px] font-semibold text-accent">{d.reference_number}</span>
                <span className="block text-[15px] text-ink">{titleWithoutRef(d.title, d.reference_number)}</span>
              </Link>
            ) : (
              <span className="block h-[60px] animate-pulse px-4 py-3" />
            )}
          </li>
        ))}
        {recent && recent.length === 0 && <li className="px-4 py-3 text-[14px] text-ink-3">Could not load the list right now.</li>}
      </ul>

      <div className="mt-8 flex flex-wrap gap-4 text-[14px] font-semibold">
        <Link href="/" className="text-accent hover:underline">
          Home
        </Link>
        <Link href="/dashboard" className="text-accent hover:underline">
          Open the library
        </Link>
      </div>
    </div>
  );
}
