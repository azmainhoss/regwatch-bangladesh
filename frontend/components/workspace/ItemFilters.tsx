"use client";

import { useCallback, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Search, X } from "lucide-react";
import type { DepartmentRead, ItemRead, MemberRead } from "@/services/workspaceApi";

export interface ItemFilterValue {
  status: string;
  department: string;
  lead: string;
  changed: boolean;
  q: string;
  sort: "deadline" | "status" | "circular";
}

export const DEFAULT_FILTER: ItemFilterValue = { status: "ALL", department: "", lead: "", changed: false, q: "", sort: "deadline" };

const STATUS_OPTIONS: [string, string][] = [
  ["ALL", "All"],
  ["NOT_STARTED", "Not started"],
  ["IN_PROGRESS", "In progress"],
  ["OVERDUE", "Overdue"],
  ["EVIDENCE_SUBMITTED", "Waiting sign-off"],
  ["COMPLIANT", "Compliant"],
  ["EXEMPTED", "Exempted"],
  ["OPEN", "All open"],
];

/** Filters live in the address, so a link from a dashboard tile opens the right view. */
export function useItemFilters(): [ItemFilterValue, (patch: Partial<ItemFilterValue>) => void, () => void] {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const value = useMemo<ItemFilterValue>(
    () => ({
      status: params.get("status") || "ALL",
      department: params.get("department") || "",
      lead: params.get("lead") || "",
      changed: params.get("changed") === "1",
      q: params.get("q") || "",
      sort: (params.get("sort") as ItemFilterValue["sort"]) || "deadline",
    }),
    [params]
  );
  const write = useCallback(
    (next: ItemFilterValue) => {
      const p = new URLSearchParams();
      if (next.status !== "ALL") p.set("status", next.status);
      if (next.department) p.set("department", next.department);
      if (next.lead) p.set("lead", next.lead);
      if (next.changed) p.set("changed", "1");
      if (next.q) p.set("q", next.q);
      if (next.sort !== "deadline") p.set("sort", next.sort);
      const s = p.toString();
      router.replace(s ? `${pathname}?${s}` : pathname, { scroll: false });
    },
    [router, pathname]
  );
  const set = useCallback((patch: Partial<ItemFilterValue>) => write({ ...value, ...patch }), [value, write]);
  const clear = useCallback(() => write(DEFAULT_FILTER), [write]);
  return [value, set, clear];
}

export function isFiltered(f: ItemFilterValue) {
  return f.status !== "ALL" || !!f.department || !!f.lead || f.changed || !!f.q;
}

const STATUS_ORDER: Record<string, number> = { OVERDUE: 0, IN_PROGRESS: 1, NOT_STARTED: 2, EVIDENCE_SUBMITTED: 3, COMPLIANT: 4, EXEMPTED: 5 };

/** Applies the filters and the sort on the client, so changing a filter is instant. */
export function applyItemFilter(items: ItemRead[], f: ItemFilterValue): ItemRead[] {
  const q = f.q.trim().toLowerCase();
  const out = items.filter((it) => {
    if (f.status === "OPEN") {
      if (!["NOT_STARTED", "IN_PROGRESS", "EVIDENCE_SUBMITTED"].includes(it.status)) return false;
    } else if (f.status !== "ALL" && it.display_status !== f.status) return false;
    if (f.department === "NONE" ? !!it.department_id : f.department && it.department_id !== f.department) return false;
    if (f.lead && it.assigned_lead?.id !== f.lead) return false;
    if (f.changed && !it.source_change) return false;
    if (q) {
      const hay = `${it.obligation_title ?? ""} ${it.source.quote ?? ""} ${it.source.reference_number ?? ""} ${it.internal_code ?? ""}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
  const cmp = (a: ItemRead, b: ItemRead) => {
    if (f.sort === "status") return (STATUS_ORDER[a.display_status] ?? 9) - (STATUS_ORDER[b.display_status] ?? 9);
    if (f.sort === "circular") return (a.source.reference_number ?? "").localeCompare(b.source.reference_number ?? "") || (a.source.page_number ?? 0) - (b.source.page_number ?? 0);
    const da = a.effective_deadline ?? "9999-12-31";
    const db = b.effective_deadline ?? "9999-12-31";
    return da < db ? -1 : da > db ? 1 : 0;
  };
  return [...out].sort(cmp);
}

export default function ItemFilters({
  value,
  onChange,
  onClear,
  departments,
  members,
}: {
  value: ItemFilterValue;
  onChange: (patch: Partial<ItemFilterValue>) => void;
  onClear: () => void;
  departments: DepartmentRead[];
  members: MemberRead[];
}) {
  return (
    <div className="space-y-3" data-testid="item-filters">
      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Status">
        {STATUS_OPTIONS.map(([key, label]) => (
          <button
            key={key}
            type="button"
            aria-pressed={value.status === key}
            onClick={() => onChange({ status: key })}
            className={`min-h-[44px] rounded-full px-3 text-[13px] font-semibold ring-1 ring-inset transition-colors sm:min-h-0 sm:py-1 ${
              value.status === key ? "bg-accent text-accent-ink ring-accent" : "bg-surface text-ink-2 ring-line-strong hover:bg-sunken"
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-[minmax(0,1.6fr)_repeat(3,minmax(0,1fr))_auto]">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3" />
          <input className="field h-11 pl-8 sm:h-9" placeholder="Search title, quote or circular" aria-label="Search items" value={value.q} onChange={(e) => onChange({ q: e.target.value })} />
        </div>
        <select className="field h-11 py-1 sm:h-9" aria-label="Department filter" value={value.department} onChange={(e) => onChange({ department: e.target.value })}>
          <option value="">All departments</option>
          <option value="NONE">No department</option>
          {departments.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>
        <select className="field h-11 py-1 sm:h-9" aria-label="Lead filter" value={value.lead} onChange={(e) => onChange({ lead: e.target.value })}>
          <option value="">All leads</option>
          {members
            .filter((m) => m.status === "ACTIVE")
            .map((m) => (
              <option key={m.id} value={m.user.id}>
                {m.user.full_name}
              </option>
            ))}
        </select>
        <select className="field h-11 py-1 sm:h-9" aria-label="Sort" value={value.sort} onChange={(e) => onChange({ sort: e.target.value as ItemFilterValue["sort"] })}>
          <option value="deadline">Sort: deadline</option>
          <option value="status">Sort: status</option>
          <option value="circular">Sort: circular</option>
        </select>
        <label className="flex min-h-[44px] items-center gap-2 text-[13.5px] font-semibold text-ink-2 sm:min-h-0">
          <input type="checkbox" className="h-4 w-4 accent-[rgb(var(--accent))]" checked={value.changed} onChange={(e) => onChange({ changed: e.target.checked })} />
          Circular changed
        </label>
      </div>
      {(value.status !== "ALL" || value.department || value.lead || value.changed || value.q) && (
        <button type="button" className="btn-ghost min-h-[44px] sm:min-h-0" onClick={onClear}>
          <X className="h-3.5 w-3.5" /> Clear filters
        </button>
      )}
    </div>
  );
}
