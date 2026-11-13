"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ChevronLeft, Loader2 } from "lucide-react";
import { EmptyState, SkeletonLine } from "@/components/ui";
import { Tag } from "@/components/StatusBadge";
import AddToRegisterModal from "@/components/workspace/AddToRegisterModal";
import { DepartmentSelect, LeadSelect } from "@/components/workspace/AssignControls";
import DeadlineField from "@/components/workspace/DeadlineField";
import { HistoryList, SignoffBox, SourceChangeBanner } from "@/components/workspace/ItemParts";
import ReasonModal from "@/components/workspace/ReasonModal";
import SourceQuote from "@/components/workspace/SourceQuote";
import TaskList from "@/components/workspace/TaskList";
import { ItemStatusBadge } from "@/components/workspace/badges";
import { LoadError } from "@/components/workspace/Shell";
import { ItemMove, allowedItemMoves, canEditItem, daysLeftText, formatDate } from "@/services/workspaceRules";
import { changeItem, itemReviewsOf, itemTasks, loadItemDetail, meOf, moveItem, useWorkspace, departmentsOf, membersOf } from "@/services/workspaceStore";

export default function ItemPage() {
  const { orgId, itemId } = useParams<{ orgId: string; itemId: string }>();
  const ws = useWorkspace();
  const me = meOf(ws, orgId);
  const item = ws.items[itemId];
  const detail = ws.loaded[`detail:${itemId}`];
  const [reasonFor, setReasonFor] = useState<ItemMove | null>(null);
  const [addFrom, setAddFrom] = useState<string | null>(null);
  const [notes, setNotes] = useState("");
  const [code, setCode] = useState("");

  useEffect(() => {
    void loadItemDetail(orgId, itemId);
  }, [orgId, itemId]);

  // Keep the text boxes in step with the saved values when they change somewhere else.
  useEffect(() => setNotes(item?.notes ?? ""), [item?.notes]);
  useEffect(() => setCode(item?.internal_code ?? ""), [item?.internal_code]);

  if (!me) return null;
  const notFound = (typeof detail === "object" && detail.error === "NOT_FOUND") || (item && item.organization_id !== orgId);
  if (notFound || (!item && typeof detail === "object")) {
    return typeof detail === "object" && detail.error !== "NOT_FOUND" ? (
      <LoadError message={detail.error} onRetry={() => void loadItemDetail(orgId, itemId)} />
    ) : (
      <EmptyState title="This item does not exist in this workspace.">
        <Link href={`/workspace/${orgId}/registers`} className="btn-secondary mt-2 min-h-[44px] sm:min-h-0">
          Back to registers
        </Link>
      </EmptyState>
    );
  }
  if (!item) {
    return (
      <div className="space-y-4" aria-busy="true" aria-label="Loading item">
        <SkeletonLine className="h-7 w-2/3" />
        <SkeletonLine className="h-28 w-full" />
        <SkeletonLine className="h-12 w-full" />
        <SkeletonLine className="h-12 w-full" />
        <SkeletonLine className="h-12 w-full" />
      </div>
    );
  }

  const tasks = itemTasks(ws, orgId, itemId);
  const liveEvidence = item.evidence_count;
  const register = ws.registers[item.register_id];
  const departments = departmentsOf(ws, orgId);
  const members = membersOf(ws, orgId);
  const canEdit = canEditItem(me, item);
  const moves = allowedItemMoves(item, me, tasks, liveEvidence);
  const lateAgainstRegulator = !!item.internal_deadline && !!item.regulatory_deadline && item.internal_deadline > item.regulatory_deadline;
  const saving = (ws.pending[itemId] ?? 0) > 0;
  const overdue = item.display_status === "OVERDUE";
  const passed = item.days_left !== null && item.days_left < 0;

  return (
    <div className="space-y-5" data-testid="item-page">
      <div>
        <Link href={register ? `/workspace/${orgId}/registers/${register.id}` : `/workspace/${orgId}/registers`} className="inline-flex min-h-[44px] items-center gap-1 text-[13px] font-semibold text-ink-3 hover:text-ink sm:min-h-0">
          <ChevronLeft className="h-4 w-4" /> {register?.title ?? "Registers"}
        </Link>
        <div className="mt-1 flex flex-wrap items-start gap-x-3 gap-y-2">
          <h2 className="min-w-0 flex-1 text-[20px] font-bold leading-snug tracking-tight text-ink">{item.obligation_title}</h2>
          <ItemStatusBadge status={item.display_status} />
          {saving && <Loader2 className="mt-1.5 h-4 w-4 animate-spin text-ink-3" aria-label="Saving" />}
        </div>
        <div className="mt-2 max-w-xs">
          <label className="sr-only" htmlFor="internal-code">
            Internal code
          </label>
          <input
            id="internal-code"
            className="field h-11 sm:h-9"
            placeholder="Internal code"
            value={code}
            disabled={!canEdit}
            maxLength={64}
            onChange={(e) => setCode(e.target.value)}
            onBlur={() => (code.trim() || null) !== (item.internal_code ?? null) && void changeItem(orgId, itemId, { internal_code: code.trim() || null })}
            onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
          />
        </div>
      </div>

      <SourceChangeBanner orgId={orgId} item={item} me={me} onAddFromNewer={(docId) => setAddFrom(docId)} />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)] lg:items-start">
        <div className="order-2 space-y-6 lg:order-1">
          <section className="panel space-y-4 px-4 py-4" aria-label="Assignment">
            <h3 className="section-title">Assignment</h3>
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="field-label" htmlFor="dept">
                  Department
                </label>
                <DepartmentSelect id="dept" item={item} me={me} departments={departments} onChange={(id) => void changeItem(orgId, itemId, { department_id: id })} className="w-full" />
              </div>
              <div>
                <label className="field-label" htmlFor="lead">
                  Lead
                </label>
                <LeadSelect id="lead" item={item} me={me} members={members} onChange={(id) => void changeItem(orgId, itemId, { assigned_lead_id: id })} className="w-full" />
              </div>
              <div>
                <label className="field-label" htmlFor="internal-deadline">
                  Internal deadline
                </label>
                <DeadlineField id="internal-deadline" label="Internal deadline" value={item.internal_deadline} disabled={!canEdit} onSave={(v) => void changeItem(orgId, itemId, { internal_deadline: v })} />
                {item.effective_deadline && (
                  <p className={`mt-1 text-[13px] ${passed ? "font-semibold text-bad" : "text-ink-3"}`} data-testid="item-days-left">
                    {passed && !overdue ? `Passed ${-(item.days_left as number)} day${item.days_left === -1 ? "" : "s"} ago` : daysLeftText(item.days_left)}
                  </p>
                )}
              </div>
              <div>
                <span className="field-label">Regulator&apos;s deadline</span>
                <p className="flex min-h-[44px] flex-col justify-center text-[14.5px] font-semibold tabular-nums text-ink sm:min-h-[36px]">
                  {formatDate(item.regulatory_deadline)}
                  {item.deadline_description && item.deadline_description !== item.regulatory_deadline && <span className="text-[12.5px] font-normal text-ink-3">{item.deadline_description}</span>}
                </p>
              </div>
            </div>
            {lateAgainstRegulator && (
              <p role="status" className="text-[13.5px] font-semibold text-warn">
                Your deadline is after the regulator&apos;s deadline.
              </p>
            )}
            <div>
              <label className="field-label" htmlFor="notes">
                Notes
              </label>
              <textarea
                id="notes"
                className="field min-h-[72px]"
                value={notes}
                disabled={!canEdit}
                maxLength={5000}
                onChange={(e) => setNotes(e.target.value)}
                onBlur={() => (notes.trim() || null) !== (item.notes ?? null) && void changeItem(orgId, itemId, { notes: notes.trim() || null })}
              />
            </div>
          </section>

          {(moves.length > 0 || item.status === "EXEMPTED") && (
            <section className="space-y-2" aria-label="Status actions" data-testid="status-actions">
              {item.status === "EXEMPTED" && item.exemption_reason && (
                <p className="text-[14px] text-ink-2">
                  <span className="font-semibold text-ink">Exempted: </span>
                  {item.exemption_reason}
                </p>
              )}
              <div className="flex flex-wrap gap-2">
                {moves.map((m) => (
                  <button
                    key={m.to}
                    type="button"
                    className={`${m.to === "EVIDENCE_SUBMITTED" ? "btn-primary" : "btn-secondary"} min-h-[44px] sm:min-h-0`}
                    disabled={!!m.disabled}
                    title={m.disabled}
                    onClick={() => (m.needsReason ? setReasonFor(m) : void moveItem(orgId, itemId, m.to))}
                  >
                    {m.label}
                  </button>
                ))}
              </div>
              {moves.filter((m) => m.disabled).map((m) => (
                <p key={m.to} className="text-[13px] text-ink-3">
                  {m.label}: {m.disabled}
                </p>
              ))}
            </section>
          )}

          <SignoffBox orgId={orgId} item={item} me={me} tasks={tasks} reviews={itemReviewsOf(ws, itemId)} />
          <TaskList orgId={orgId} item={item} tasks={tasks} me={me} members={members} />
          <HistoryList orgId={orgId} itemId={itemId} />
        </div>

        <aside className="order-1 space-y-4 lg:order-2" aria-label="Source">
          <section className="panel space-y-4 px-4 py-4">
            <h3 className="section-title">Source</h3>
            <SourceQuote item={item} />
          </section>
          {(item.requirement_description || item.applicability_summary) && (
            <section className="panel space-y-3 px-4 py-4">
              {item.requirement_description && (
                <div>
                  <h3 className="section-title">What it requires</h3>
                  <p className="mt-1 text-[14.5px] leading-relaxed text-ink-2">{item.requirement_description}</p>
                </div>
              )}
              {item.applicability_summary && (
                <div>
                  <h3 className="section-title">Who it applies to</h3>
                  <p className="mt-1 text-[14.5px] leading-relaxed text-ink-2">{item.applicability_summary}</p>
                </div>
              )}
              <div className="flex flex-wrap gap-2">
                {item.obligation_type && <Tag tone="accent">{item.obligation_type.charAt(0) + item.obligation_type.slice(1).toLowerCase().replace(/_/g, " ")}</Tag>}
                {item.frequency && item.frequency !== "ONE_TIME" && <Tag tone="muted">{item.frequency.charAt(0) + item.frequency.slice(1).toLowerCase().replace(/_/g, " ")}</Tag>}
              </div>
            </section>
          )}
        </aside>
      </div>

      <ReasonModal
        open={!!reasonFor}
        onClose={() => setReasonFor(null)}
        title={reasonFor?.to === "EXEMPTED" ? "Exempt this item" : "Reopen this item"}
        confirmLabel={reasonFor?.to === "EXEMPTED" ? "Exempt" : "Reopen"}
        onConfirm={(r) => reasonFor && void moveItem(orgId, itemId, reasonFor.to, r)}
      />
      <AddToRegisterModal open={!!addFrom} onClose={() => setAddFrom(null)} orgId={orgId} registerId={item.register_id} initialDocumentId={addFrom} />
    </div>
  );
}
