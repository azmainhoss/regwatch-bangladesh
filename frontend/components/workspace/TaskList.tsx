"use client";

import { useEffect, useState } from "react";
import { ChevronDown, Pencil, Plus, XCircle } from "lucide-react";
import { PriorityTag, TaskStatusBadge } from "./badges";
import ReasonModal from "./ReasonModal";
import { EvidenceList, EvidenceUpload, ReviewBox, TaskEditor } from "./TaskParts";
import type { ItemRead, MemberRead, TaskRead } from "@/services/workspaceApi";
import {
  Me,
  addDays,
  dhakaToday,
  canChangeTaskStatus,
  canEditTasks,
  canUploadEvidence,
  daysLeftText,
  formatDate,
} from "@/services/workspaceRules";
import { cancelTaskNow, changeTask, taskEvidence, taskReviewsOf, useWorkspace } from "@/services/workspaceStore";

function TaskCard({ orgId, task, item, me, members, open, onToggle }: { orgId: string; task: TaskRead; item: ItemRead; me: Me; members: MemberRead[]; open: boolean; onToggle: () => void }) {
  const ws = useWorkspace();
  const [editing, setEditing] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const evidence = taskEvidence(ws, task.id);
  const reviews = taskReviewsOf(ws, task.id);
  const uploads = Object.values(ws.uploads).filter((u) => u.taskId === task.id);
  const closedItem = item.status === "COMPLIANT" || item.status === "EXEMPTED";
  const editable = canEditTasks(me, item) && !closedItem && task.status !== "APPROVED" && task.status !== "CANCELLED";
  const canToggle = canChangeTaskStatus(me, task, item) && (task.status === "PENDING" || task.status === "IN_PROGRESS");
  const canUpload = canUploadEvidence(me, task, item) && !closedItem && task.status !== "APPROVED" && task.status !== "CANCELLED";
  const tmp = task.id.startsWith("tmp:");
  return (
    <li id={`task-${task.id}`} data-testid="task" data-task-id={task.id} className={`rounded-panel border border-line bg-surface ${tmp ? "opacity-70" : ""}`}>
      <button type="button" onClick={onToggle} aria-expanded={open} className="flex min-h-[56px] w-full items-start gap-3 px-3.5 py-3 text-left">
        <ChevronDown className={`mt-1 h-4 w-4 shrink-0 text-ink-3 transition-transform ${open ? "" : "-rotate-90"}`} />
        <span className="min-w-0 flex-1">
          <span className={`block text-[15px] font-semibold ${task.status === "CANCELLED" ? "text-ink-3 line-through" : "text-ink"}`}>{task.title}</span>
          <span className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-ink-3">
            <span>{task.assigned_to ? task.assigned_to.full_name : "Not assigned"}</span>
            <span className={task.is_overdue ? "font-semibold text-bad" : ""}>
              Due {formatDate(task.due_date)}
              {task.days_left !== null && task.status !== "APPROVED" && task.status !== "CANCELLED" ? `, ${daysLeftText(task.days_left).toLowerCase()}` : ""}
            </span>
            <PriorityTag priority={task.priority} />
          </span>
        </span>
        <TaskStatusBadge status={task.status} />
      </button>
      {open && (
        <div className="space-y-4 border-t border-line px-3.5 py-3.5">
          {task.description && <p className="whitespace-pre-line text-[14px] text-ink-2">{task.description}</p>}
          {task.status === "CANCELLED" && task.cancelled_reason && <p className="text-[13.5px] text-ink-3">Cancelled: {task.cancelled_reason}</p>}
          <div className="flex flex-wrap gap-2">
            {canToggle && (
              <button
                type="button"
                className="btn-secondary min-h-[44px] sm:min-h-0"
                onClick={() => void changeTask(orgId, task.id, { status: task.status === "PENDING" ? "IN_PROGRESS" : "PENDING" })}
              >
                {task.status === "PENDING" ? "Mark as in progress" : "Move back to to do"}
              </button>
            )}
            {editable && (
              <>
                <button type="button" className="btn-secondary min-h-[44px] sm:min-h-0" onClick={() => setEditing(true)}>
                  <Pencil className="h-3.5 w-3.5" /> Edit
                </button>
                <button type="button" className="btn-ghost min-h-[44px] text-bad sm:min-h-0" onClick={() => setCancelling(true)}>
                  <XCircle className="h-3.5 w-3.5" /> Cancel task
                </button>
              </>
            )}
          </div>
          <div className="space-y-2">
            <h4 className="text-[13px] font-semibold text-ink-2">Evidence</h4>
            <EvidenceList orgId={orgId} task={task} evidence={evidence} me={me} canWithdrawAny />
            {canUpload && <EvidenceUpload orgId={orgId} task={task} uploads={uploads} />}
          </div>
          <ReviewBox orgId={orgId} task={task} item={item} me={me} reviews={reviews} />
        </div>
      )}
      <TaskEditor open={editing} onClose={() => setEditing(false)} orgId={orgId} item={item} task={task} members={members} defaultDue={task.due_date} />
      <ReasonModal open={cancelling} onClose={() => setCancelling(false)} title="Cancel this task" confirmLabel="Cancel task" danger onConfirm={(r) => void cancelTaskNow(orgId, task.id, r)} />
    </li>
  );
}

export default function TaskList({ orgId, item, tasks, me, members }: { orgId: string; item: ItemRead; tasks: TaskRead[]; me: Me; members: MemberRead[] }) {
  const [adding, setAdding] = useState(false);
  const [openIds, setOpenIds] = useState<Record<string, boolean>>({});
  const closedItem = item.status === "COMPLIANT" || item.status === "EXEMPTED";
  const canAdd = canEditTasks(me, item) && !closedItem;
  const defaultDue = item.effective_deadline || addDays(dhakaToday(), 14);

  // A link such as #task-<id> opens that task.
  useEffect(() => {
    const hash = typeof window !== "undefined" ? window.location.hash : "";
    if (hash.startsWith("#task-")) {
      const id = hash.slice(6);
      setOpenIds((o) => ({ ...o, [id]: true }));
      setTimeout(() => document.getElementById(`task-${id}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 150);
    }
  }, [tasks.length]);

  return (
    <section aria-label="Tasks" data-testid="task-list">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="section-title">
          Tasks <span className="font-normal text-ink-3 tabular-nums">{tasks.length}</span>
        </h3>
        {canAdd && (
          <button type="button" className="btn-secondary min-h-[44px] sm:min-h-0" onClick={() => setAdding(true)} data-testid="add-task">
            <Plus className="h-4 w-4" /> Add task
          </button>
        )}
      </div>
      {tasks.length === 0 ? (
        <p className="rounded-panel border border-dashed border-line-strong px-4 py-6 text-center text-[14px] text-ink-3">No tasks yet. Add one to start collecting evidence.</p>
      ) : (
        <ul className="space-y-2.5">
          {tasks.map((t) => (
            <TaskCard key={t.id} orgId={orgId} task={t} item={item} me={me} members={members} open={!!openIds[t.id]} onToggle={() => setOpenIds((o) => ({ ...o, [t.id]: !o[t.id] }))} />
          ))}
        </ul>
      )}
      <TaskEditor open={adding} onClose={() => setAdding(false)} orgId={orgId} item={item} members={members} defaultDue={defaultDue} />
    </section>
  );
}
