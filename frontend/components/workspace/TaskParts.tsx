"use client";

import { useEffect, useId, useRef, useState } from "react";
import { Download, FileText, Loader2, RotateCw, Upload, X } from "lucide-react";
import { Modal, ModalHeader } from "../ui";
import { TaskStatusBadge } from "./badges";
import ReasonModal from "./ReasonModal";
import type { EvidenceRead, ItemRead, MemberRead, TaskRead, TaskReviewRead } from "@/services/workspaceApi";
import { downloadEvidence } from "@/services/workspaceApi";
import {
  Me,
  SELF_REVIEW_TASK,
  canDownload,
  canReviewTaskRole,
  checkEvidenceFile,
  formatBytes,
  formatDateTime,
  taskReviewBlock,
} from "@/services/workspaceRules";
import {
  UploadRow,
  addTask,
  changeTask,
  decideTask,
  dismissUpload,
  retryUpload,
  setNotice,
  startUpload,
  withdrawFile,
} from "@/services/workspaceStore";

// ------------------------------------------------------------------------------------ editor
export function TaskEditor({
  open,
  onClose,
  orgId,
  item,
  task,
  members,
  defaultDue,
}: {
  open: boolean;
  onClose: () => void;
  orgId: string;
  item: ItemRead;
  task?: TaskRead;
  members: MemberRead[];
  defaultDue: string;
}) {
  const id = useId();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [assignee, setAssignee] = useState("");
  const [due, setDue] = useState(defaultDue);
  const [priority, setPriority] = useState("MEDIUM");

  useEffect(() => {
    if (!open) return;
    setTitle(task?.title ?? "");
    setDescription(task?.description ?? "");
    setAssignee(task?.assigned_to_user_id ?? "");
    setDue(task?.due_date ?? defaultDue);
    setPriority(task?.priority ?? "MEDIUM");
  }, [open, task, defaultDue]);

  const active = members.filter((m) => m.status === "ACTIVE");
  const ok = title.trim().length > 0 && !!due;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!ok) return;
    if (task) {
      const change: Record<string, unknown> = {};
      if (title.trim() !== task.title) change.title = title.trim();
      if ((description.trim() || null) !== (task.description ?? null)) change.description = description.trim() || null;
      if ((assignee || null) !== (task.assigned_to_user_id ?? null)) change.assigned_to_user_id = assignee || null;
      if (due !== task.due_date) change.due_date = due;
      if (priority !== task.priority) change.priority = priority;
      if (Object.keys(change).length) void changeTask(orgId, task.id, change);
    } else {
      void addTask(orgId, item.id, { title: title.trim(), description: description.trim() || null, assigned_to_user_id: assignee || null, due_date: due, priority });
    }
    onClose();
  };

  return (
    <Modal open={open} onClose={onClose} labelledBy={`${id}-title`} width="max-w-lg">
      <ModalHeader id={`${id}-title`} title={task ? "Edit task" : "Add a task"} subtitle={item.obligation_title ?? undefined} onClose={onClose} />
      <form onSubmit={submit} className="max-h-[70dvh] space-y-4 overflow-y-auto px-5 py-4">
        <div>
          <label className="field-label" htmlFor={`${id}-t`}>
            What needs to be done
          </label>
          <input id={`${id}-t`} className="field h-11 sm:h-9" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={255} required />
        </div>
        <div>
          <label className="field-label" htmlFor={`${id}-d`}>
            Details (optional)
          </label>
          <textarea id={`${id}-d`} className="field min-h-[72px]" value={description} onChange={(e) => setDescription(e.target.value)} maxLength={5000} />
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className="field-label" htmlFor={`${id}-a`}>
              Assigned to
            </label>
            <select id={`${id}-a`} className="field h-11 py-1 sm:h-9" value={assignee} onChange={(e) => setAssignee(e.target.value)}>
              <option value="">No one yet</option>
              {active.map((m) => (
                <option key={m.id} value={m.user.id}>
                  {m.user.full_name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="field-label" htmlFor={`${id}-due`}>
              Due date
            </label>
            <input id={`${id}-due`} type="date" className="field h-11 sm:h-9" value={due} onChange={(e) => setDue(e.target.value)} required />
          </div>
        </div>
        <div>
          <label className="field-label" htmlFor={`${id}-p`}>
            Priority
          </label>
          <select id={`${id}-p`} className="field h-11 py-1 sm:h-9" value={priority} onChange={(e) => setPriority(e.target.value)}>
            <option value="LOW">Low</option>
            <option value="MEDIUM">Medium</option>
            <option value="HIGH">High</option>
            <option value="CRITICAL">Critical</option>
          </select>
        </div>
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-ghost min-h-[44px] sm:min-h-0" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" disabled={!ok} className="btn-primary min-h-[44px] sm:min-h-0">
            {task ? "Save" : "Add task"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

// ------------------------------------------------------------------------------------ evidence

export function EvidenceList({
  orgId,
  task,
  evidence,
  me,
  canWithdrawAny,
}: {
  orgId: string;
  task: TaskRead;
  evidence: EvidenceRead[];
  me: Me;
  canWithdrawAny: boolean;
}) {
  const [withdrawing, setWithdrawing] = useState<EvidenceRead | null>(null);
  const [downloading, setDownloading] = useState<string | null>(null);
  if (evidence.length === 0) return <p className="text-[13.5px] text-ink-3">No evidence files yet.</p>;
  return (
    <>
      <ul className="divide-y divide-line rounded-control border border-line" data-testid="evidence-list">
        {evidence.map((e) => {
          const withdrawn = !!e.withdrawn_at;
          const mine = e.submitted_by_user_id === me.userId;
          return (
            <li key={e.id} className="flex flex-col gap-1.5 px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <div className={`flex items-center gap-1.5 text-[14px] font-semibold ${withdrawn ? "text-ink-3 line-through" : "text-ink"}`}>
                  <FileText className="h-4 w-4 shrink-0" strokeWidth={1.75} />
                  <span className="min-w-0 break-all">{e.original_filename}</span>
                </div>
                <div className="mt-0.5 flex flex-wrap items-center gap-x-3 text-[12.5px] text-ink-3">
                  <span>{formatBytes(e.file_size_bytes)}</span>
                  <span>
                    {e.submitted_by.full_name}, {formatDateTime(e.created_at)}
                  </span>
                </div>
                {e.notes && <p className="mt-0.5 text-[13px] text-ink-2">{e.notes}</p>}
                {withdrawn && (
                  <p className="mt-0.5 text-[12.5px] text-ink-3">
                    Withdrawn{e.withdrawn_by ? ` by ${e.withdrawn_by.full_name}` : ""}, {formatDateTime(e.withdrawn_at)}
                  </p>
                )}
              </div>
              <div className="flex shrink-0 gap-1.5">
                {canDownload(me) && (
                  <button
                    type="button"
                    className="btn-secondary min-h-[44px] sm:min-h-0"
                    disabled={downloading === e.id}
                    onClick={async () => {
                      setDownloading(e.id);
                      try {
                        await downloadEvidence(orgId, task.id, e.id, e.original_filename);
                      } catch (err: any) {
                        setNotice({ kind: "error", text: `Could not download the file: ${err?.message || "unknown error"}` });
                      } finally {
                        setDownloading(null);
                      }
                    }}
                  >
                    {downloading === e.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" strokeWidth={1.75} />}
                    Download
                  </button>
                )}
                {!withdrawn && mine && canWithdrawAny && task.status !== "APPROVED" && (
                  <button type="button" className="btn-ghost min-h-[44px] sm:min-h-0" onClick={() => setWithdrawing(e)}>
                    Withdraw
                  </button>
                )}
              </div>
            </li>
          );
        })}
      </ul>
      <ReasonModal
        open={!!withdrawing}
        onClose={() => setWithdrawing(null)}
        title="Withdraw this file"
        subtitle="The file stays in the record, marked as withdrawn."
        confirmLabel="Withdraw"
        danger
        onConfirm={(reason) => withdrawing && void withdrawFile(orgId, task.id, withdrawing.id, reason)}
      />
    </>
  );
}

export function EvidenceUpload({ orgId, task, uploads }: { orgId: string; task: TaskRead; uploads: UploadRow[] }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [notes, setNotes] = useState("");
  const [drag, setDrag] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  const take = (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setLocalError(null);
    const file = files[0];
    const problem = checkEvidenceFile(file);
    if (problem) {
      setLocalError(problem);
      return;
    }
    void startUpload(orgId, task.id, file, notes);
    setNotes("");
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <div className="space-y-2" data-testid="evidence-upload">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          take(e.dataTransfer.files);
        }}
        className={`flex flex-col gap-2 rounded-control border border-dashed p-3 sm:flex-row sm:items-center ${drag ? "border-accent bg-accent-soft" : "border-line-strong"}`}
      >
        <input ref={inputRef} type="file" className="sr-only" id={`file-${task.id}`} aria-label="Choose an evidence file" accept=".pdf,.png,.jpg,.jpeg,.docx,.xlsx,.csv,.txt" onChange={(e) => take(e.target.files)} />
        <label htmlFor={`file-${task.id}`} className="btn-secondary min-h-[44px] cursor-pointer sm:min-h-0">
          <Upload className="h-4 w-4" strokeWidth={1.75} />
          Choose a file
        </label>
        <span className="hidden text-[13px] text-ink-3 sm:inline">or drop it here. PDF, PNG, JPG, DOCX, XLSX, CSV or TXT, up to 25 MB.</span>
        <span className="text-[12.5px] text-ink-3 sm:hidden">PDF, PNG, JPG, DOCX, XLSX, CSV or TXT, up to 25 MB.</span>
        <input className="field h-11 sm:ml-auto sm:h-9 sm:max-w-[16rem]" placeholder="Note (optional)" aria-label="Evidence note" value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={500} />
      </div>
      {localError && (
        <p role="alert" className="text-[13.5px] text-bad">
          {localError}
        </p>
      )}
      {uploads.map((u) => (
        <div key={u.id} data-testid="upload-row" className={`rounded-control border px-3 py-2 text-[13.5px] ${u.state === "error" ? "border-bad/40 bg-bad-soft" : "border-line bg-sunken/60"}`}>
          <div className="flex items-center justify-between gap-2">
            <span className="min-w-0 break-all font-semibold text-ink">{u.fileName}</span>
            <span className="shrink-0 text-ink-3">{formatBytes(u.size)}</span>
          </div>
          {u.state === "uploading" ? (
            <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-line" role="progressbar" aria-valuenow={Math.round(u.progress * 100)} aria-valuemin={0} aria-valuemax={100}>
              <div className="h-full bg-accent transition-[width]" style={{ width: `${Math.max(4, Math.round(u.progress * 100))}%` }} />
            </div>
          ) : (
            <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
              <span className="text-bad">{u.error}</span>
              <span className="flex gap-1">
                <button type="button" className="btn-secondary min-h-[44px] sm:min-h-0" onClick={() => void retryUpload(u.id)}>
                  <RotateCw className="h-3.5 w-3.5" /> Try again
                </button>
                <button type="button" className="btn-ghost min-h-[44px] sm:min-h-0" onClick={() => dismissUpload(u.id)} aria-label="Dismiss">
                  <X className="h-4 w-4" />
                </button>
              </span>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------------------------ review
export function ReviewBox({ orgId, task, item, me, reviews }: { orgId: string; task: TaskRead; item: ItemRead; me: Me; reviews: TaskReviewRead[] }) {
  const [comments, setComments] = useState("");
  const [sendBack, setSendBack] = useState<"CHANGES_REQUESTED" | "REJECTED" | null>(null);
  const allowedRole = canReviewTaskRole(me, item);
  const block = taskReviewBlock(me, task);
  const waiting = task.status === "SUBMITTED";
  return (
    <div className="space-y-3" id={`review-${task.id}`}>
      {waiting && allowedRole && (
        <div className="rounded-control border border-warn/30 bg-warn-soft px-3 py-3">
          <p className="text-[13.5px] font-semibold text-ink">Evidence is waiting for review.</p>
          {block ? (
            <p className="mt-1 text-[13.5px] text-ink-2" data-testid="self-review-note">
              {block || SELF_REVIEW_TASK}
            </p>
          ) : (
            <>
              <textarea className="field mt-2 min-h-[64px]" placeholder="Comment (needed to ask for changes or reject)" aria-label="Review comment" value={comments} onChange={(e) => setComments(e.target.value)} maxLength={2000} />
              <div className="mt-2 flex flex-wrap gap-2">
                <button
                  type="button"
                  className="btn-primary min-h-[44px] sm:min-h-0"
                  onClick={() => {
                    void decideTask(orgId, task.id, "APPROVED", comments.trim());
                    setComments("");
                  }}
                >
                  Approve
                </button>
                <button type="button" className="btn-secondary min-h-[44px] sm:min-h-0" onClick={() => setSendBack("CHANGES_REQUESTED")}>
                  Ask for changes
                </button>
                <button type="button" className="btn-danger min-h-[44px] sm:min-h-0" onClick={() => setSendBack("REJECTED")}>
                  Reject
                </button>
              </div>
            </>
          )}
        </div>
      )}
      {reviews.length > 0 && (
        <ul className="space-y-1.5" aria-label="Past reviews">
          {reviews.map((r) => (
            <li key={r.id} className="rounded-control bg-sunken/60 px-3 py-2 text-[13.5px]">
              <span className="font-semibold text-ink">{r.decision === "APPROVED" ? "Approved" : r.decision === "REJECTED" ? "Rejected" : "Changes requested"}</span>{" "}
              <span className="text-ink-3">
                by {r.reviewer.full_name}, {formatDateTime(r.created_at)}
              </span>
              {r.comments && <p className="mt-0.5 text-ink-2">{r.comments}</p>}
            </li>
          ))}
        </ul>
      )}
      <ReasonModal
        open={!!sendBack}
        onClose={() => setSendBack(null)}
        title={sendBack === "REJECTED" ? "Reject this evidence" : "Ask for changes"}
        label="Comment"
        initial={comments}
        confirmLabel={sendBack === "REJECTED" ? "Reject" : "Ask for changes"}
        danger={sendBack === "REJECTED"}
        onConfirm={(text) => {
          if (sendBack) void decideTask(orgId, task.id, sendBack, text);
          setComments("");
        }}
      />
    </div>
  );
}

export { TaskStatusBadge };
