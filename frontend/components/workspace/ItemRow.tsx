"use client";

import { memo } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { Tag } from "../StatusBadge";
import { ItemStatusBadge } from "./badges";
import { DepartmentSelect, LeadSelect } from "./AssignControls";
import type { DepartmentRead, ItemRead, MemberRead } from "@/services/workspaceApi";
import { Me, daysLeftText, formatDate } from "@/services/workspaceRules";
import { changeItem } from "@/services/workspaceStore";

function circularLabel(item: ItemRead) {
  const ref = item.source.reference_number || "Circular";
  return item.source.page_number ? `${ref}, p. ${item.source.page_number}` : ref;
}

/** One item of a register: a table row on wide screens, a card on phones. Pickers save on change. */
function ItemRow({
  item,
  orgId,
  me,
  departments,
  members,
  busy,
}: {
  item: ItemRead;
  orgId: string;
  me: Me;
  departments: DepartmentRead[];
  members: MemberRead[];
  busy: boolean;
}) {
  const router = useRouter();
  const href = `/workspace/${orgId}/items/${item.id}`;
  const pendingNew = item.id.startsWith("tmp:");
  // A deadline that has passed shows in red even when the bank has done its part (waiting sign-off, compliant).
  const overdue = item.display_status === "OVERDUE";
  const passed = item.days_left !== null && item.days_left < 0;
  const dayText = passed && !overdue ? `Passed ${-(item.days_left as number)} day${item.days_left === -1 ? "" : "s"} ago` : daysLeftText(item.days_left);
  const tasks = item.task_counts;
  return (
    <div
      data-testid="item-row"
      data-item-id={item.id}
      onClick={(e) => {
        if (pendingNew) return;
        if ((e.target as HTMLElement).closest("select, button, input, a, label")) return;
        router.push(href);
      }}
      className={`grid cursor-pointer gap-3 px-4 py-3.5 transition-colors hover:bg-sunken/60 lg:grid-cols-[minmax(0,2.4fr)_minmax(0,1.2fr)_minmax(0,1.2fr)_minmax(0,0.9fr)_minmax(0,1fr)] lg:items-start lg:gap-4 ${
        pendingNew ? "opacity-60" : ""
      }`}
    >
      <div className="min-w-0">
        <div className="flex items-start gap-2">
          {pendingNew ? (
            <span className="text-[15px] font-semibold leading-snug text-ink">{item.obligation_title}</span>
          ) : (
            <Link href={href} className="text-[15px] font-semibold leading-snug text-ink hover:text-accent">
              {item.obligation_title || "Obligation"}
            </Link>
          )}
          {busy && <Loader2 className="mt-1 h-3.5 w-3.5 shrink-0 animate-spin text-ink-3" aria-label="Saving" />}
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] text-ink-3">
          <span className="font-semibold tabular-nums text-accent">{circularLabel(item)}</span>
          {item.internal_code && <span>{item.internal_code}</span>}
          {item.source_change && (
            <Tag tone="warn" title={item.source_change.detail}>
              Circular changed
            </Tag>
          )}
          {pendingNew && <span>Adding…</span>}
        </div>
      </div>

      <div className="min-w-0" onClick={(e) => e.stopPropagation()}>
        <span className="mb-1 block text-2xs font-semibold uppercase tracking-wide text-ink-3 lg:hidden">Department</span>
        <DepartmentSelect item={item} me={me} departments={departments} onChange={(id) => changeItem(orgId, item.id, { department_id: id })} className="w-full" />
      </div>
      <div className="min-w-0" onClick={(e) => e.stopPropagation()}>
        <span className="mb-1 block text-2xs font-semibold uppercase tracking-wide text-ink-3 lg:hidden">Lead</span>
        <LeadSelect item={item} me={me} members={members} onChange={(id) => changeItem(orgId, item.id, { assigned_lead_id: id })} className="w-full" />
      </div>

      <div className="min-w-0 text-[13.5px]">
        <span className="mb-0.5 block text-2xs font-semibold uppercase tracking-wide text-ink-3 lg:hidden">Deadline</span>
        <span className={`font-semibold tabular-nums ${passed ? "text-bad" : "text-ink"}`} data-testid="item-deadline">
          {formatDate(item.effective_deadline)}
        </span>
        {item.effective_deadline && <span className={`block text-[12.5px] ${passed ? "text-bad" : "text-ink-3"}`}>{dayText}</span>}
      </div>

      <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 lg:block lg:space-y-1">
        <ItemStatusBadge status={item.display_status} />
        <span className="block text-[12.5px] text-ink-3">{tasks.total > 0 ? `${tasks.approved} of ${tasks.total} tasks approved` : "No tasks yet"}</span>
      </div>
    </div>
  );
}

export default memo(ItemRow);
