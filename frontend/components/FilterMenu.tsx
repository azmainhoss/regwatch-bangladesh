"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronDown, Search, X } from "lucide-react";

export interface FilterOption {
  code: string;
  label: string;
  sub?: string;
  count?: number;
}

/**
 * A button that opens a searchable list: a popover on wide screens, a bottom sheet on phones.
 * Used for "More departments" and "Category" on the dashboard.
 */
export default function FilterMenu({
  label,
  title,
  options,
  value,
  onChange,
  active = false,
  placeholder = "Search",
}: {
  label: React.ReactNode;
  title: string;
  options: FilterOption[];
  value: string;
  onChange: (code: string) => void;
  active?: boolean;
  placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const box = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setQ("");
    const t = window.setTimeout(() => input.current?.focus(), 30);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    const onDown = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onDown);
    return () => {
      window.clearTimeout(t);
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onDown);
    };
  }, [open]);

  const shown = useMemo(() => {
    const s = q.trim().toLowerCase();
    return s ? options.filter((o) => `${o.label} ${o.sub ?? ""} ${o.code}`.toLowerCase().includes(s)) : options;
  }, [q, options]);

  const pick = (code: string) => {
    onChange(code);
    setOpen(false);
  };

  return (
    <div ref={box} className="relative shrink-0">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="listbox"
        className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-3.5 py-1.5 text-[13.5px] font-semibold transition-colors ${
          active ? "border-accent bg-accent text-accent-ink" : "border-line bg-surface text-ink-2 hover:border-accent/50 hover:text-ink"
        }`}
      >
        {label}
        <ChevronDown className="h-3.5 w-3.5" strokeWidth={2.25} />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40 bg-ink/20 sm:hidden" aria-hidden onClick={() => setOpen(false)} />
          <div
            role="dialog"
            aria-label={title}
            className="fixed inset-x-0 bottom-0 z-50 max-h-[75dvh] rounded-t-[16px] border border-line bg-surface pb-[env(safe-area-inset-bottom)] shadow-pop sm:absolute sm:inset-x-auto sm:bottom-auto sm:left-0 sm:top-[calc(100%+6px)] sm:max-h-[420px] sm:w-[340px] sm:rounded-[12px] sm:pb-0"
          >
            <div className="flex items-center justify-between px-4 pb-1 pt-3 sm:hidden">
              <p className="text-[15px] font-bold text-ink">{title}</p>
              <button type="button" onClick={() => setOpen(false)} aria-label="Close" className="grid h-8 w-8 place-items-center text-ink-3">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="relative px-3 pt-2 sm:pt-3">
              <Search className="pointer-events-none absolute left-6 top-1/2 mt-0.5 h-4 w-4 -translate-y-1/2 text-ink-3 sm:mt-1" strokeWidth={1.75} />
              <input ref={input} value={q} onChange={(e) => setQ(e.target.value)} placeholder={placeholder} className="field h-10 pl-9" aria-label={placeholder} />
            </div>
            <ul role="listbox" aria-label={title} className="mt-2 max-h-[calc(75dvh-120px)] overflow-y-auto px-1.5 pb-2 sm:max-h-[330px]">
              {shown.length === 0 && <li className="px-3 py-3 text-[14px] text-ink-3">No match</li>}
              {shown.map((o) => {
                const on = o.code === value;
                return (
                  <li key={o.code}>
                    <button
                      type="button"
                      role="option"
                      aria-selected={on}
                      onClick={() => pick(o.code)}
                      className={`flex w-full items-center gap-3 rounded-[8px] px-3 py-2.5 text-left hover:bg-sunken ${on ? "bg-accent-soft" : ""}`}
                    >
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[14px] font-semibold text-ink">{o.label}</span>
                        {o.sub && <span className="block truncate text-[12.5px] text-ink-3">{o.sub}</span>}
                      </span>
                      {typeof o.count === "number" && o.count >= 0 && <span className="text-[12.5px] tabular-nums text-ink-3">{o.count.toLocaleString("en-US")}</span>}
                      {on && <Check className="h-4 w-4 text-accent" strokeWidth={2.5} />}
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        </>
      )}
    </div>
  );
}
