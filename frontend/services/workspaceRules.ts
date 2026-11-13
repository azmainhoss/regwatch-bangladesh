/**
 * Plain rules for the compliance workspace (no React). They mirror backend/app/modules/compliance/rules.py
 * and permissions.py, so the browser can show overdue badges and hide controls without waiting for the server.
 * The server is the final check.
 */
import type {
  DepartmentRead,
  DisplayStatus,
  EvidenceRead,
  ItemRead,
  ItemStatus,
  MemberRead,
  TaskRead,
  TaskStatus,
} from "./workspaceApi";

const DHAKA = "Asia/Dhaka";

// ------------------------------------------------------------------------------------ dates
/** Today's date in Dhaka, as YYYY-MM-DD. */
export function dhakaToday(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: DHAKA, year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
}

/** Milliseconds until the next midnight in Dhaka (plus a second so the date has changed). */
export function msUntilDhakaMidnight(now: Date = new Date()): number {
  const parts = new Intl.DateTimeFormat("en-GB", { timeZone: DHAKA, hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" }).formatToParts(now);
  const get = (t: string) => Number(parts.find((p) => p.type === t)?.value ?? 0);
  const secondsLeft = 24 * 3600 - (get("hour") * 3600 + get("minute") * 60 + get("second"));
  return (secondsLeft + 1) * 1000;
}

function dayNumber(iso: string): number {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return Math.round(Date.UTC(y, m - 1, d) / 86400000);
}

/** Whole days from `today` to `deadline` (negative when past). Null without a deadline. */
export function daysLeft(deadline: string | null | undefined, today: string): number | null {
  return deadline ? dayNumber(deadline) - dayNumber(today) : null;
}

export function addDays(iso: string, days: number): string {
  const d = new Date((dayNumber(iso) + days) * 86400000);
  return d.toISOString().slice(0, 10);
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "Not set";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: DHAKA });
}

export function daysLeftText(days: number | null): string {
  if (days === null) return "";
  if (days === 0) return "Due today";
  if (days === 1) return "1 day left";
  if (days > 1) return `${days} days left`;
  if (days === -1) return "1 day overdue";
  return `${-days} days overdue`;
}

// ------------------------------------------------------------------------------------ status
export const OPEN_STATUSES: ItemStatus[] = ["NOT_STARTED", "IN_PROGRESS", "EVIDENCE_SUBMITTED"];
const OVERDUE_ITEM = new Set<string>(["NOT_STARTED", "IN_PROGRESS"]);
const OVERDUE_TASK = new Set<string>(["PENDING", "IN_PROGRESS", "REJECTED"]);

export function effectiveDeadline(item: Pick<ItemRead, "internal_deadline" | "regulatory_deadline">): string | null {
  return item.internal_deadline || item.regulatory_deadline || null;
}

export function isItemOverdue(item: Pick<ItemRead, "status" | "internal_deadline" | "regulatory_deadline">, today: string): boolean {
  const d = effectiveDeadline(item);
  return OVERDUE_ITEM.has(item.status) && !!d && d < today;
}

export function displayStatus(item: Pick<ItemRead, "status" | "internal_deadline" | "regulatory_deadline">, today: string): DisplayStatus {
  return isItemOverdue(item, today) ? "OVERDUE" : item.status;
}

export function isTaskOverdue(task: Pick<TaskRead, "status" | "due_date">, today: string): boolean {
  return OVERDUE_TASK.has(task.status) && task.due_date < today;
}

export const ITEM_STATUS_LABEL: Record<string, string> = {
  NOT_STARTED: "Not started",
  IN_PROGRESS: "In progress",
  OVERDUE: "Overdue",
  EVIDENCE_SUBMITTED: "Waiting sign-off",
  COMPLIANT: "Compliant",
  EXEMPTED: "Exempted",
};
export const TASK_STATUS_LABEL: Record<string, string> = {
  PENDING: "To do",
  IN_PROGRESS: "In progress",
  SUBMITTED: "Evidence submitted",
  APPROVED: "Approved",
  REJECTED: "Rejected",
  CANCELLED: "Cancelled",
};
export type BadgeTone = "ok" | "warn" | "bad" | "info" | "muted";
export const ITEM_STATUS_TONE: Record<string, BadgeTone> = {
  NOT_STARTED: "muted",
  IN_PROGRESS: "info",
  OVERDUE: "bad",
  EVIDENCE_SUBMITTED: "warn",
  COMPLIANT: "ok",
  EXEMPTED: "muted",
};
export const TASK_STATUS_TONE: Record<string, BadgeTone> = {
  PENDING: "muted",
  IN_PROGRESS: "info",
  SUBMITTED: "warn",
  APPROVED: "ok",
  REJECTED: "bad",
  CANCELLED: "muted",
};

// ------------------------------------------------------------------------------------ files
export const EVIDENCE_MAX_BYTES = 25 * 1024 * 1024;
export const EVIDENCE_EXTENSIONS = ["pdf", "png", "jpg", "jpeg", "docx", "xlsx", "csv", "txt"];
export const EVIDENCE_TYPE_ERROR = "Allowed files: PDF, PNG, JPG, DOCX, XLSX, CSV, TXT.";

/** Checks a file before any request is made. Returns an error text, or null when it looks fine. */
export function checkEvidenceFile(file: { name: string; size: number }): string | null {
  const ext = file.name.includes(".") ? file.name.split(".").pop()!.toLowerCase() : "";
  if (!EVIDENCE_EXTENSIONS.includes(ext)) return EVIDENCE_TYPE_ERROR;
  if (file.size === 0) return "That file is empty.";
  if (file.size > EVIDENCE_MAX_BYTES) return "File is larger than 25 MB.";
  return null;
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

// ------------------------------------------------------------------------------------ permissions
/** The signed-in user's place in one organization. */
export interface Me {
  userId: string;
  role: string;
  departmentId: string | null;
}

export function meFrom(m: MemberRead): Me {
  return { userId: m.user.id, role: m.role, departmentId: m.department_id };
}

const EDITORS = new Set(["ORG_ADMIN", "COMPLIANCE_HEAD", "COMPLIANCE_OFFICER"]);
type ItemLike = Pick<ItemRead, "department_id" | "assigned_lead">;
type TaskLike = Pick<TaskRead, "assigned_to_user_id">;

export function ownDepartment(me: Me, item: ItemLike): boolean {
  return !!me.departmentId && me.departmentId === item.department_id;
}
export function isItemLead(me: Me, item: ItemLike): boolean {
  return !!item.assigned_lead && item.assigned_lead.id === me.userId;
}
export function canEditItem(me: Me, item: ItemLike): boolean {
  return EDITORS.has(me.role) || (me.role === "DEPARTMENT_LEAD" && ownDepartment(me, item));
}
export function canStartItem(me: Me, item: ItemLike): boolean {
  return canEditItem(me, item) || (me.role === "ANALYST" && isItemLead(me, item));
}
export function canEditTasks(me: Me, item: ItemLike): boolean {
  return canStartItem(me, item);
}
export function canChangeTaskStatus(me: Me, task: TaskLike, item: ItemLike): boolean {
  return canEditTasks(me, item) || (!["AUDITOR", "VIEWER"].includes(me.role) && task.assigned_to_user_id === me.userId);
}
export function canUploadEvidence(me: Me, task: TaskLike, item: ItemLike): boolean {
  return canChangeTaskStatus(me, task, item);
}
export function canReviewTaskRole(me: Me, item: ItemLike): boolean {
  return ["ORG_ADMIN", "COMPLIANCE_HEAD", "REVIEWER"].includes(me.role) || (me.role === "DEPARTMENT_LEAD" && ownDepartment(me, item));
}
export function canSignOffRole(me: Me): boolean {
  return ["ORG_ADMIN", "COMPLIANCE_HEAD", "REVIEWER"].includes(me.role);
}
export function canExemptOrReopen(me: Me): boolean {
  return me.role === "ORG_ADMIN" || me.role === "COMPLIANCE_HEAD";
}
export function canAcknowledge(me: Me): boolean {
  return EDITORS.has(me.role);
}
export function canDownload(me: Me): boolean {
  return me.role !== "VIEWER";
}

export const SELF_REVIEW_TASK = "You uploaded evidence here, so another reviewer must decide.";
export const SELF_REVIEW_ITEM = "You worked on this item, so another reviewer must decide.";

/** Why the user may not review this task (they uploaded evidence on it or it is theirs), or null. */
export function taskReviewBlock(me: Me, task: Pick<TaskRead, "assigned_to_user_id" | "uploader_ids">): string | null {
  if (task.assigned_to_user_id === me.userId || task.uploader_ids.includes(me.userId)) return SELF_REVIEW_TASK;
  return null;
}

/** Why the user may not sign off the item (they sent it, or uploaded evidence on one of its tasks), or null. */
export function signoffBlock(me: Me, item: Pick<ItemRead, "submitted_for_signoff_by">, tasks: Pick<TaskRead, "uploader_ids">[]): string | null {
  if (item.submitted_for_signoff_by?.id === me.userId) return SELF_REVIEW_ITEM;
  if (tasks.some((t) => t.uploader_ids.includes(me.userId))) return SELF_REVIEW_ITEM;
  return null;
}

export interface ItemMove {
  to: "IN_PROGRESS" | "EVIDENCE_SUBMITTED" | "EXEMPTED" | "NOT_STARTED" | "REOPEN";
  label: string;
  /** A reason is typed by the person before the move is made. */
  needsReason: boolean;
  /** Plain words for why the move cannot be made right now (the button shows disabled with this as a hint). */
  disabled?: string;
}

/** The status moves open to this user for this item right now. */
export function allowedItemMoves(item: ItemRead, me: Me, tasks: Pick<TaskRead, "status">[], evidenceCount: number): ItemMove[] {
  const moves: ItemMove[] = [];
  const live = tasks.filter((t) => t.status !== "CANCELLED");
  if (item.status === "NOT_STARTED" && canStartItem(me, item)) moves.push({ to: "IN_PROGRESS", label: "Start", needsReason: false });
  if (item.status === "IN_PROGRESS" && canStartItem(me, item)) {
    let disabled: string | undefined;
    if (live.length === 0) disabled = "Add a task first.";
    else if (live.some((t) => t.status !== "APPROVED")) disabled = "Approve all tasks first.";
    else if (evidenceCount === 0) disabled = "Add at least one evidence file.";
    moves.push({ to: "EVIDENCE_SUBMITTED", label: "Send for sign-off", needsReason: false, disabled });
  }
  if (canExemptOrReopen(me)) {
    if (item.status !== "COMPLIANT" && item.status !== "EXEMPTED") moves.push({ to: "EXEMPTED", label: "Exempt", needsReason: true });
    if (item.status === "EXEMPTED") moves.push({ to: "NOT_STARTED", label: "Remove exemption", needsReason: false });
    if (item.status === "COMPLIANT") moves.push({ to: "REOPEN", label: "Reopen", needsReason: true });
  }
  return moves;
}

// ------------------------------------------------------------------------------------ summaries
export interface DeptRow {
  departmentId: string | null;
  name: string;
  open: number;
  overdue: number;
  waiting: number;
  compliant: number;
  exempted: number;
  total: number;
}

export interface DashboardData {
  total: number;
  open: number;
  overdue: number;
  waiting: number;
  flagged: number;
  compliant: number;
  exempted: number;
  upcoming: { kind: "item" | "task"; id: string; itemId: string; title: string; date: string; days: number; departmentId: string | null; status: string; overdue: boolean }[];
  overdueList: DashboardData["upcoming"];
  byDepartment: DeptRow[];
}

/** Everything the dashboard shows, from the items and tasks in the store. */
export function summarize(
  items: ItemRead[],
  tasks: TaskRead[],
  departments: Pick<DepartmentRead, "id" | "name">[],
  today: string
): DashboardData {
  const horizon = addDays(today, 30);
  const out: DashboardData = { total: items.length, open: 0, overdue: 0, waiting: 0, flagged: 0, compliant: 0, exempted: 0, upcoming: [], overdueList: [], byDepartment: [] };
  const byItem: Record<string, ItemRead> = {};
  const rows = new Map<string | null, DeptRow>();
  const rowFor = (id: string | null) => {
    let r = rows.get(id);
    if (!r) {
      r = { departmentId: id, name: id ? departments.find((d) => d.id === id)?.name ?? "Department" : "No department", open: 0, overdue: 0, waiting: 0, compliant: 0, exempted: 0, total: 0 };
      rows.set(id, r);
    }
    return r;
  };
  for (const d of departments) rowFor(d.id);

  for (const it of items) {
    byItem[it.id] = it;
    const overdue = isItemOverdue(it, today);
    const row = rowFor(it.department_id);
    row.total++;
    if (OPEN_STATUSES.includes(it.status)) {
      out.open++;
      row.open++;
    }
    if (overdue) {
      out.overdue++;
      row.overdue++;
    }
    if (it.status === "EVIDENCE_SUBMITTED") {
      out.waiting++;
      row.waiting++;
    }
    if (it.status === "COMPLIANT") {
      out.compliant++;
      row.compliant++;
    }
    if (it.status === "EXEMPTED") {
      out.exempted++;
      row.exempted++;
    }
    if (it.source_change) out.flagged++;
    const eff = effectiveDeadline(it);
    if (eff && OPEN_STATUSES.includes(it.status)) {
      const entry = { kind: "item" as const, id: it.id, itemId: it.id, title: it.obligation_title || "Obligation", date: eff, days: daysLeft(eff, today) ?? 0, departmentId: it.department_id, status: displayStatus(it, today), overdue };
      if (overdue) out.overdueList.push(entry);
      else if (eff <= horizon) out.upcoming.push(entry);
    }
  }
  for (const t of tasks) {
    const item = byItem[t.compliance_item_id];
    if (!item) continue;
    if (!["PENDING", "IN_PROGRESS", "REJECTED", "SUBMITTED"].includes(t.status)) continue;
    const overdue = isTaskOverdue(t, today);
    const entry = { kind: "task" as const, id: t.id, itemId: item.id, title: t.title, date: t.due_date, days: daysLeft(t.due_date, today) ?? 0, departmentId: item.department_id, status: t.status, overdue };
    if (overdue) out.overdueList.push(entry);
    else if (t.due_date <= horizon) out.upcoming.push(entry);
  }
  const byDate = (a: { date: string; title: string }, b: { date: string; title: string }) => (a.date === b.date ? a.title.localeCompare(b.title) : a.date < b.date ? -1 : 1);
  out.upcoming.sort(byDate);
  out.overdueList.sort(byDate);
  out.byDepartment = Array.from(rows.values())
    .filter((r) => r.total > 0 || r.departmentId !== null)
    .sort((a, b) => (a.departmentId === null ? 1 : b.departmentId === null ? -1 : a.name.localeCompare(b.name)));
  return out;
}

export interface RegisterCountsView {
  total: number;
  not_started: number;
  in_progress: number;
  evidence_submitted: number;
  compliant: number;
  exempted: number;
  overdue: number;
  flagged: number;
}

export function countItems(items: ItemRead[], today: string): RegisterCountsView {
  const c: RegisterCountsView = { total: items.length, not_started: 0, in_progress: 0, evidence_submitted: 0, compliant: 0, exempted: 0, overdue: 0, flagged: 0 };
  for (const it of items) {
    const s = displayStatus(it, today);
    if (s === "NOT_STARTED") c.not_started++;
    else if (s === "IN_PROGRESS") c.in_progress++;
    else if (s === "EVIDENCE_SUBMITTED") c.evidence_submitted++;
    else if (s === "COMPLIANT") c.compliant++;
    else if (s === "EXEMPTED") c.exempted++;
    else c.overdue++;
    if (it.source_change) c.flagged++;
  }
  return c;
}

export function sourceChangeText(item: Pick<ItemRead, "source_change">): string {
  return item.source_change?.detail ?? "";
}

/** One plain sentence for an audit entry. */
export function describeAudit(e: { action: string; entity_type: string; actor: { full_name: string } | null; before: any; after: any }, names: (userId: string | null | undefined) => string): string {
  const who = e.actor?.full_name ?? "Someone";
  const a = e.after || {};
  const b = e.before || {};
  const status = (s: string) => ITEM_STATUS_LABEL[s] ?? TASK_STATUS_LABEL[s] ?? s;
  switch (e.action) {
    case "ITEM_ADDED":
      return `${who} added this item to a register`;
    case "ITEM_UPDATED": {
      const parts: string[] = [];
      if ("department_id" in a) parts.push("the department");
      if ("assigned_lead_id" in a) parts.push(`the lead from ${names(b.assigned_lead_id)} to ${names(a.assigned_lead_id)}`);
      if ("internal_deadline" in a) parts.push(`the internal deadline from ${b.internal_deadline ? formatDate(b.internal_deadline) : "not set"} to ${a.internal_deadline ? formatDate(a.internal_deadline) : "not set"}`);
      if ("internal_code" in a) parts.push("the internal code");
      if ("notes" in a) parts.push("the notes");
      return `${who} changed ${parts.join(", ") || "the item"}`;
    }
    case "ITEM_STATUS_CHANGED":
    case "ITEM_SIGNED_OFF": {
      const text = `${who} moved the item from ${status(b.status ?? "")} to ${status(a.status ?? "")}`;
      return a.reason ? `${text} (${a.reason})` : text;
    }
    case "ITEM_SOURCE_CHANGE_ACKNOWLEDGED":
      return `${who} marked the circular change as reviewed${a.note ? `: ${a.note}` : ""}`;
    case "TASK_CREATED":
      return `${who} added the task "${a.title ?? ""}"`;
    case "TASK_UPDATED":
      return `${who} changed the task${a.title ? ` "${a.title}"` : ""}`;
    case "TASK_STATUS_CHANGED": {
      const text = `${who} moved a task from ${status(b.status ?? "")} to ${status(a.status ?? "")}`;
      return a.reason ? `${text} (${a.reason})` : text;
    }
    case "TASK_REVIEWED":
      return `${who} reviewed a task: ${String(a.decision || "").toLowerCase().replace(/_/g, " ")}${a.comments ? ` (${a.comments})` : ""}`;
    case "EVIDENCE_UPLOADED":
      return `${who} uploaded ${a.filename ?? "a file"}`;
    case "EVIDENCE_WITHDRAWN":
      return `${who} withdrew an evidence file${a.reason ? ` (${a.reason})` : ""}`;
    case "EVIDENCE_DOWNLOADED":
      return `${who} downloaded ${a.filename ?? "an evidence file"}`;
    case "REGISTER_CREATED":
      return `${who} created the register "${a.title ?? ""}"`;
    case "REGISTER_UPDATED":
      return `${who} changed the register`;
    case "MEMBER_ADDED":
      return `${who} added ${a.email ?? "a member"} as ${a.role ?? "a member"}`;
    case "MEMBER_UPDATED":
      return `${who} changed a member`;
    case "DEPARTMENT_CREATED":
      return `${who} added the department "${a.name ?? ""}"`;
    case "DEPARTMENT_UPDATED":
      return `${who} changed a department`;
    case "DEPARTMENT_DELETED":
      return `${who} deleted the department "${b.name ?? ""}"`;
    case "REPORT_EXPORTED":
      return `${who} exported the ${a.format ?? ""} report`;
    default:
      return `${who}: ${e.action.toLowerCase().replace(/_/g, " ")}`;
  }
}
