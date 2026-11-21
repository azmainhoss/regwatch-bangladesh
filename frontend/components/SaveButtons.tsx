"use client";

import { useEffect, useRef, useState } from "react";
import { Bookmark, Check, ListPlus, Plus, Star } from "lucide-react";
import { createList, isIn, listOfKind, toggle, toggleKind, useLists } from "@/services/listsStore";

/** Star (Favourites) and bookmark (Read later). Both change the instant they are tapped. */
export function QuickSave({ documentId, size = "md", onNeedSignIn }: { documentId: string; size?: "sm" | "md"; onNeedSignIn?: () => void }) {
  const s = useLists();
  const fav = listOfKind(s, "FAVOURITES");
  const later = listOfKind(s, "READ_LATER");
  const isFav = isIn(s, fav?.id, documentId);
  const isLater = isIn(s, later?.id, documentId);
  const box = size === "sm" ? "h-7 w-7" : "h-9 w-9";
  const icon = size === "sm" ? "h-3.5 w-3.5" : "h-4 w-4";
  const signedOut = !s.userId;
  const tap = (kind: "FAVOURITES" | "READ_LATER") => (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    if (signedOut) return onNeedSignIn?.();
    toggleKind(kind, documentId);
  };
  return (
    <span className="inline-flex items-center gap-0.5">
      <button
        type="button"
        onClick={tap("FAVOURITES")}
        aria-pressed={isFav}
        aria-label={isFav ? "Remove from favourites" : "Add to favourites"}
        title={isFav ? "In favourites" : "Add to favourites"}
        className={`grid ${box} place-items-center rounded-control transition-colors hover:bg-sunken ${isFav ? "text-amber-500" : "text-ink-3 hover:text-ink"}`}
      >
        <Star className={icon} strokeWidth={1.9} fill={isFav ? "currentColor" : "none"} />
      </button>
      <button
        type="button"
        onClick={tap("READ_LATER")}
        aria-pressed={isLater}
        aria-label={isLater ? "Remove from read later" : "Read later"}
        title={isLater ? "In read later" : "Read later"}
        className={`grid ${box} place-items-center rounded-control transition-colors hover:bg-sunken ${isLater ? "text-accent" : "text-ink-3 hover:text-ink"}`}
      >
        <Bookmark className={icon} strokeWidth={1.9} fill={isLater ? "currentColor" : "none"} />
      </button>
    </span>
  );
}

/** "Add to list": the person's own lists with a tick on the ones holding this circular, plus "New list". */
export function AddToList({ documentId, onNeedSignIn }: { documentId: string; onNeedSignIn?: () => void }) {
  const s = useLists();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const custom = s.lists.filter((l) => l.kind === "CUSTOM");
  const count = custom.filter((l) => l.document_ids.includes(documentId)).length;

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  const make = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || busy) return;
    setBusy(true);
    try {
      await createList(name.trim(), documentId);
      setName("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => (s.userId ? setOpen((o) => !o) : onNeedSignIn?.())}
        aria-expanded={open}
        className="btn-secondary h-9 gap-1.5 px-3 text-[13.5px]"
      >
        <ListPlus className="h-4 w-4" strokeWidth={1.9} />
        {count > 0 ? `In ${count} ${count === 1 ? "list" : "lists"}` : "Add to list"}
      </button>
      {open && (
        <div className="absolute right-0 z-30 mt-1.5 w-64 rounded-panel border border-line bg-surface p-1.5 shadow-lg">
          {custom.length === 0 && <p className="px-2.5 py-2 text-[13px] text-ink-3">No lists yet. Name one below.</p>}
          <ul className="max-h-64 overflow-y-auto">
            {custom.map((l) => {
              const on = l.document_ids.includes(documentId);
              return (
                <li key={l.id}>
                  <button
                    type="button"
                    onClick={() => toggle(l.id, documentId, !on)}
                    className="flex w-full items-center justify-between gap-2 rounded-control px-2.5 py-2 text-left text-[14px] text-ink hover:bg-sunken"
                  >
                    <span className="truncate">{l.name}</span>
                    <span className="flex items-center gap-2 text-[12px] text-ink-3">
                      {l.document_ids.length}
                      <span className={`grid h-4 w-4 place-items-center rounded border ${on ? "border-accent bg-accent text-accent-ink" : "border-line"}`}>
                        {on && <Check className="h-3 w-3" strokeWidth={2.5} />}
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
          <form onSubmit={make} className="mt-1 flex gap-1 border-t border-line pt-1.5">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="New list name"
              aria-label="New list name"
              maxLength={120}
              className="field h-8 flex-1 px-2 text-[13.5px]"
            />
            <button type="submit" disabled={!name.trim() || busy} className="btn-primary h-8 px-2" aria-label="Make list">
              <Plus className="h-4 w-4" />
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
