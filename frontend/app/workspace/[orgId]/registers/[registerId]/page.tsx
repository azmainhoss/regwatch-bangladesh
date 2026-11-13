"use client";

import { Suspense, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ChevronLeft, Plus } from "lucide-react";
import { EmptyState } from "@/components/ui";
import { Tag } from "@/components/StatusBadge";
import AddToRegisterModal from "@/components/workspace/AddToRegisterModal";
import ItemFilters, { applyItemFilter, isFiltered, useItemFilters } from "@/components/workspace/ItemFilters";
import ItemRow from "@/components/workspace/ItemRow";
import { ListSkeleton } from "@/components/workspace/Shell";
import { countItems } from "@/services/workspaceRules";
import { meOf, orgItems, registerItems, useWorkspace, departmentsOf, membersOf } from "@/services/workspaceStore";

function RegisterView() {
  const { orgId, registerId } = useParams<{ orgId: string; registerId: string }>();
  const ws = useWorkspace();
  const [filter, setFilter, clear] = useItemFilters();
  const [adding, setAdding] = useState(false);
  const me = meOf(ws, orgId);
  const perms = ws.me[orgId]?.permissions;
  const isAll = registerId === "all";
  const register = isAll ? null : ws.registers[registerId];
  const loaded = ws.loaded[`items:${orgId}`] === "ok" && ws.loaded[`registers:${orgId}`] === "ok";
  const all = isAll ? orgItems(ws, orgId) : registerItems(ws, orgId, registerId);
  const departments = departmentsOf(ws, orgId);
  const members = membersOf(ws, orgId);
  const items = useMemo(() => applyItemFilter(all, filter), [all, filter]);
  const counts = countItems(all, ws.today);

  if (!me) return null;
  if (loaded && !isAll && (!register || register.organization_id !== orgId)) {
    return (
      <EmptyState title="This register does not exist in this workspace.">
        <Link href={`/workspace/${orgId}/registers`} className="btn-secondary mt-2 min-h-[44px] sm:min-h-0">
          Back to registers
        </Link>
      </EmptyState>
    );
  }
  const pendingIds = new Set(Object.entries(ws.pending).filter(([, n]) => n > 0).map(([id]) => id));

  return (
    <div className="space-y-4" data-testid="register-view">
      <div>
        <Link href={`/workspace/${orgId}/registers`} className="inline-flex min-h-[44px] items-center gap-1 text-[13px] font-semibold text-ink-3 hover:text-ink sm:min-h-0">
          <ChevronLeft className="h-4 w-4" /> Registers
        </Link>
        <div className="mt-1 flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-[20px] font-bold tracking-tight text-ink">{isAll ? "All registers" : register?.title}</h2>
            {register?.description && <p className="mt-0.5 text-[14px] text-ink-3">{register.description}</p>}
            <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-ink-3 tabular-nums">
              <span>{counts.total} items</span>
              <span>{counts.compliant} compliant</span>
              <span>{counts.in_progress} in progress</span>
              <span className={counts.overdue ? "font-semibold text-bad" : ""}>{counts.overdue} overdue</span>
              <span>{counts.not_started} not started</span>
              {register && !register.is_active && <Tag tone="muted">Archived</Tag>}
            </p>
          </div>
          {!isAll && perms?.add_items && register?.is_active && (
            <button type="button" className="btn-primary min-h-[44px] sm:min-h-0" onClick={() => setAdding(true)} data-testid="add-from-circular">
              <Plus className="h-4 w-4" /> Add from a circular
            </button>
          )}
        </div>
      </div>

      {!loaded ? (
        <ListSkeleton rows={4} />
      ) : all.length === 0 ? (
        <EmptyState title="This register has no items yet.">
          {!isAll && perms?.add_items ? (
            <button type="button" className="btn-primary mt-2 min-h-[44px] sm:min-h-0" onClick={() => setAdding(true)}>
              Add from a circular
            </button>
          ) : (
            <Link href="/" className="btn-secondary mt-2 min-h-[44px] sm:min-h-0">
              Browse circulars
            </Link>
          )}
        </EmptyState>
      ) : (
        <>
          <ItemFilters value={filter} onChange={setFilter} onClear={clear} departments={departments} members={members} />
          {items.length === 0 ? (
            <EmptyState title="No items match these filters.">
              {isFiltered(filter) && (
                <button type="button" className="btn-secondary mt-2 min-h-[44px] sm:min-h-0" onClick={clear}>
                  Clear filters
                </button>
              )}
            </EmptyState>
          ) : (
            <div className="panel overflow-hidden">
              <div className="hidden grid-cols-[minmax(0,2.4fr)_minmax(0,1.2fr)_minmax(0,1.2fr)_minmax(0,0.9fr)_minmax(0,1fr)] gap-4 border-b border-line px-4 py-2 text-[12.5px] font-semibold text-ink-3 lg:grid">
                <span>Obligation</span>
                <span>Department</span>
                <span>Lead</span>
                <span>Deadline</span>
                <span>Status</span>
              </div>
              <div className="divide-y divide-line" data-testid="item-list">
                {items.map((it) => (
                  <ItemRow key={it.id} item={it} orgId={orgId} me={me} departments={departments} members={members} busy={pendingIds.has(it.id)} />
                ))}
              </div>
            </div>
          )}
        </>
      )}
      {!isAll && register && <AddToRegisterModal open={adding} onClose={() => setAdding(false)} orgId={orgId} registerId={register.id} />}
    </div>
  );
}

export default function RegisterViewPage() {
  return (
    <Suspense fallback={<ListSkeleton rows={4} />}>
      <RegisterView />
    </Suspense>
  );
}
