"use client";

import { useEffect, useState } from "react";
import { ArrowUpRight, Loader2 } from "lucide-react";
import { apiFetch } from "@/services/api";

// One copy of each opened PDF per tab session, so switching panels or circulars back and forth is instant.
const cache = new Map<string, string>();

/** The original PDF from Bangladesh Bank, shown inside the side panel. */
export default function PdfPanel({ documentId, page }: { documentId: string; page?: number }) {
  const [url, setUrl] = useState<string | null>(cache.get(documentId) ?? null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setError(null);
    const known = cache.get(documentId);
    if (known) {
      setUrl(known);
      return;
    }
    setUrl(null);
    apiFetch(`/documents/${documentId}/pdf`, { cache: "no-store" })
      .then(async (res) => {
        if (!res.ok) throw new Error("The original PDF could not be loaded.");
        const blob = await res.blob();
        const u = URL.createObjectURL(new Blob([blob], { type: "application/pdf" }));
        cache.set(documentId, u);
        if (alive) setUrl(u);
      })
      .catch((e) => alive && setError(e.message || "The original PDF could not be loaded."));
    return () => {
      alive = false;
    };
  }, [documentId]);

  const src = url ? `${url}#page=${page || 1}&view=FitH` : null;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between gap-2 border-b border-line px-3 py-2 text-[13px] text-ink-3">
        <span>The file exactly as Bangladesh Bank published it.</span>
        {url && (
          <a href={url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-semibold text-accent hover:underline">
            Open in new tab <ArrowUpRight className="h-3.5 w-3.5" />
          </a>
        )}
      </div>
      <div className="min-h-0 flex-1 bg-sunken">
        {error ? (
          <p className="p-4 text-[14px] text-danger">{error}</p>
        ) : src ? (
          <iframe key={src} src={src} title="Original PDF" className="h-full w-full border-0" />
        ) : (
          <p className="flex items-center gap-2 p-4 text-[14px] text-ink-3">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading the PDF...
          </p>
        )}
      </div>
    </div>
  );
}
