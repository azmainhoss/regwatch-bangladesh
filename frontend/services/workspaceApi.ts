/**
 * Calls for the bank compliance workspace. Types match the backend schemas in
 * backend/app/modules/compliance/schemas.py and organizations/schemas.py.
 */
import { ApiError, apiFetch, getApiBaseUrl, getAuthToken } from "./api";

// ------------------------------------------------------------------------------------ types
export type Role =
  | "ORG_ADMIN"
  | "COMPLIANCE_HEAD"
  | "COMPLIANCE_OFFICER"
  | "DEPARTMENT_LEAD"
  | "REVIEWER"
  | "ANALYST"
  | "AUDITOR"
  | "VIEWER";

export const ROLE_LABEL: Record<string, string> = {
  ORG_ADMIN: "Admin",
  COMPLIANCE_HEAD: "Compliance head",
  COMPLIANCE_OFFICER: "Compliance officer",
  DEPARTMENT_LEAD: "Department lead",
  REVIEWER: "Reviewer",
  ANALYST: "Department staff",
  AUDITOR: "Internal audit",
  VIEWER: "Viewer",
};
export const ROLES: Role[] = ["ORG_ADMIN", "COMPLIANCE_HEAD", "COMPLIANCE_OFFICER", "DEPARTMENT_LEAD", "REVIEWER", "ANALYST", "AUDITOR", "VIEWER"];

export type ItemStatus = "NOT_STARTED" | "IN_PROGRESS" | "EVIDENCE_SUBMITTED" | "COMPLIANT" | "EXEMPTED";
export type DisplayStatus = ItemStatus | "OVERDUE";
export type TaskStatus = "PENDING" | "IN_PROGRESS" | "SUBMITTED" | "APPROVED" | "REJECTED" | "CANCELLED";
export type Priority = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export interface UserMini {
  id: string;
  full_name: string;
  email: string;
}

export interface MemberRead {
  id: string;
  organization_id: string;
  user: UserMini;
  role: Role | string;
  department_id: string | null;
  status: string;
  created_at: string;
}

export interface DepartmentRead {
  id: string;
  organization_id: string;
  name: string;
  head_user_id: string | null;
  head: UserMini | null;
  member_count: number;
  open_item_count: number;
  created_at: string;
}

export interface MyOrg {
  id: string;
  name: string;
  entity_type: string;
  role: string;
  department_id: string | null;
}

export interface Permissions {
  manage_members: boolean;
  manage_departments: boolean;
  manage_registers: boolean;
  add_items: boolean;
  edit_any_item: boolean;
  exempt_and_reopen: boolean;
  sign_off_items: boolean;
  review_tasks: boolean;
  view_audit_log: boolean;
  export_report: boolean;
  download_evidence: boolean;
}

export interface MeInOrg {
  membership: MemberRead;
  permissions: Permissions;
}

export interface DocRef {
  id: string;
  reference_number: string | null;
  title: string;
}

export interface SourceRef {
  document_id: string | null;
  version_id: string | null;
  reference_number: string | null;
  title: string | null;
  publication_date: string | null;
  page_number: number | null;
  quote: string | null;
  quote_span_ids: any;
  quote_boxes: any;
  file_sha256: string | null;
  page_link: string | null;
  in_force_status: string;
  in_force_by: DocRef | null;
  current_version_id: string | null;
  is_withdrawn: boolean;
}

export interface SourceChange {
  kind: "AMENDED" | "REPLACED" | "REPEALED" | "NEW_VERSION" | "WITHDRAWN";
  by: DocRef | null;
  detail: string;
}

export interface TaskCounts {
  total: number;
  open: number;
  submitted: number;
  approved: number;
  overdue: number;
}

export interface ItemRead {
  id: string;
  organization_id: string;
  register_id: string;
  internal_code: string | null;
  obligation_id: string | null;
  obligation_title: string | null;
  requirement_description: string | null;
  obligation_type: string | null;
  applicability_summary: string | null;
  frequency: string | null;
  regulatory_deadline: string | null;
  deadline_description: string | null;
  internal_deadline: string | null;
  effective_deadline: string | null;
  status: ItemStatus;
  display_status: DisplayStatus;
  is_overdue: boolean;
  days_left: number | null;
  department_id: string | null;
  assigned_lead: UserMini | null;
  notes: string | null;
  exemption_reason: string | null;
  submitted_for_signoff_by: UserMini | null;
  submitted_for_signoff_at: string | null;
  signed_off_by: UserMini | null;
  signed_off_at: string | null;
  source: SourceRef;
  source_change: SourceChange | null;
  task_counts: TaskCounts;
  evidence_count: number;
  lock_version: number;
  created_at: string;
  updated_at: string;
}

export interface TaskRead {
  id: string;
  organization_id: string;
  compliance_item_id: string;
  title: string;
  description: string | null;
  assigned_to_user_id: string | null;
  assigned_to: UserMini | null;
  due_date: string;
  priority: Priority | string;
  status: TaskStatus;
  is_overdue: boolean;
  days_left: number | null;
  cancelled_reason: string | null;
  evidence_count: number;
  uploader_ids: string[];
  lock_version: number;
  created_at: string;
  updated_at: string;
}

export interface EvidenceRead {
  id: string;
  task_id: string;
  organization_id: string;
  submitted_by_user_id: string;
  submitted_by: UserMini;
  file_sha256: string;
  original_filename: string;
  file_size_bytes: number;
  mime_type: string | null;
  notes: string | null;
  created_at: string;
  withdrawn_at: string | null;
  withdrawn_by: UserMini | null;
}

export interface TaskReviewRead {
  id: string;
  task_id: string;
  reviewer_user_id: string;
  reviewer: UserMini;
  decision: string;
  comments: string;
  evidence_ids: string[] | null;
  created_at: string;
}

export interface ItemReviewRead {
  id: string;
  item_id: string;
  reviewer: UserMini;
  decision: string;
  comments: string;
  created_at: string;
}

export interface AuditRead {
  id: string;
  action: string;
  entity_type: string;
  entity_id: string;
  actor: UserMini | null;
  before: any;
  after: any;
  created_at: string;
}

export interface ItemCounts {
  total: number;
  not_started: number;
  in_progress: number;
  evidence_submitted: number;
  compliant: number;
  exempted: number;
  overdue: number;
  flagged: number;
}

export interface RegisterRead {
  id: string;
  organization_id: string;
  title: string;
  description: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  item_counts: ItemCounts;
  source_document_ids: string[];
}

export interface Skipped {
  obligation_id: string;
  reason: string;
}

export interface AddableObligation {
  id: string;
  title: string;
  obligation_type: string;
  page_number: number | null;
  quote: string;
  regulatory_deadline: string | null;
  verification_status: string;
  addable: boolean;
  reason_not_addable: string | null;
  already_in_register_ids: string[];
}

export interface AddableObligations {
  document: {
    id: string;
    reference_number: string | null;
    title: string;
    publication_status: string;
    in_force_status: string;
    in_force_by: DocRef | null;
    current_version_id: string | null;
  };
  obligations: AddableObligation[];
}

export interface ReportData {
  organization: { id: string; name: string };
  generated_at: string;
  as_of: string;
  generated_by: UserMini;
  register_id: string | null;
  register_title: string | null;
  totals: Record<string, number>;
  by_department: { department_id: string | null; name: string; total: number; open: number; overdue: number; evidence_submitted: number; compliant: number; exempted: number }[];
  overdue_items: ItemRead[];
  upcoming_items: ItemRead[];
  flagged_items: ItemRead[];
  items: ItemRead[];
}

// ------------------------------------------------------------------------------------ plumbing
/** An API error that may carry the server's current copy of the record (HTTP 409). */
export class WorkspaceError extends ApiError {
  current: any;
  constructor(status: number, message: string, current?: any) {
    super(status, message);
    this.name = "WorkspaceError";
    this.current = current;
  }
}

function messageFrom(body: any, status: number): string {
  const detail = body?.detail ?? body?.message;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail
      .map((d: any) => {
        const loc = Array.isArray(d?.loc) ? d.loc.filter((x: any) => x !== "body").join(".") : "";
        return loc ? `${loc}: ${d?.msg ?? ""}` : d?.msg ?? "";
      })
      .join("; ");
  }
  return `Request failed (HTTP ${status})`;
}

async function fail(res: Response): Promise<never> {
  const body = await res.json().catch(() => null);
  throw new WorkspaceError(res.status, messageFrom(body, res.status), body?.current);
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await apiFetch(path, {
    method,
    cache: "no-store",
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) await fail(res);
  if (res.status === 204) return undefined as T;
  return res.json();
}

function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const parts = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== "")
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  return parts.length ? `?${parts.join("&")}` : "";
}

const org = (id: string) => `/organizations/${id}`;
const comp = (id: string) => `/organizations/${id}/compliance`;

// ------------------------------------------------------------------------------------ organization
export const fetchMyOrgs = () => call<MyOrg[]>("GET", "/organizations/mine");
export const createOrganization = (name: string, entity_type: string) => call<{ id: string; name: string }>("POST", "/organizations", { name, entity_type });
export const fetchMe = (o: string) => call<MeInOrg>("GET", `${org(o)}/me`);
export const fetchMembers = (o: string) => call<MemberRead[]>("GET", `${org(o)}/members`);
export const fetchDepartments = (o: string) => call<DepartmentRead[]>("GET", `${org(o)}/departments`);
export const addMemberByEmail = (o: string, body: { email: string; role: string; department_id?: string | null }) => call<MemberRead>("POST", `${org(o)}/members/by-email`, body);
export const updateMember = (o: string, id: string, body: { role?: string; department_id?: string | null; status?: string }) => call<MemberRead>("PATCH", `${org(o)}/members/${id}`, body);
export const createDepartment = (o: string, body: { name: string; head_user_id?: string | null }) => call<DepartmentRead>("POST", `${org(o)}/departments`, body);
export const updateDepartment = (o: string, id: string, body: { name?: string; head_user_id?: string | null }) => call<DepartmentRead>("PATCH", `${org(o)}/departments/${id}`, body);
export const deleteDepartment = (o: string, id: string) => call<void>("DELETE", `${org(o)}/departments/${id}`);

// ------------------------------------------------------------------------------------ registers and items
export const fetchRegisters = (o: string) => call<RegisterRead[]>("GET", `${comp(o)}/registers${qs({ include_archived: true })}`);
export const createRegister = (o: string, body: { title: string; description?: string | null }) => call<RegisterRead>("POST", `${comp(o)}/registers`, body);
export const updateRegister = (o: string, id: string, body: { title?: string; description?: string | null; is_active?: boolean }) => call<RegisterRead>("PATCH", `${comp(o)}/registers/${id}`, body);
export const createRegisterFromDocument = (o: string, body: { document_id: string; title?: string; obligation_ids?: string[] }) =>
  call<{ register: RegisterRead; items: ItemRead[]; skipped: Skipped[] }>("POST", `${comp(o)}/registers/from-document`, body);
export const addItemsFromDocument = (o: string, registerId: string, body: { document_id: string; obligation_ids?: string[] }) =>
  call<{ items: ItemRead[]; skipped: Skipped[] }>("POST", `${comp(o)}/registers/${registerId}/items/from-document`, body);
export const fetchAddable = (o: string, documentId: string) => call<AddableObligations>("GET", `${comp(o)}/documents/${documentId}/addable-obligations`);

export interface Page<T> {
  total: number;
  as_of: string;
  server_time: string;
  rows: T[];
}
export async function fetchItems(o: string, params: { updated_since?: string; limit?: number; offset?: number } = {}): Promise<Page<ItemRead>> {
  const r = await call<{ items: ItemRead[]; total: number; as_of: string; server_time: string }>("GET", `${comp(o)}/items${qs({ limit: 500, ...params })}`);
  return { rows: r.items, total: r.total, as_of: r.as_of, server_time: r.server_time };
}
export interface ItemDetail {
  item: ItemRead;
  tasks: TaskRead[];
  evidence: EvidenceRead[];
  task_reviews: TaskReviewRead[];
  item_reviews: ItemReviewRead[];
}
export const fetchItemDetail = (o: string, id: string) => call<ItemDetail>("GET", `${comp(o)}/items/${id}`);
export const patchItem = (o: string, id: string, body: Record<string, unknown>) => call<ItemRead>("PATCH", `${comp(o)}/items/${id}`, body);
export const changeItemStatus = (o: string, id: string, body: { to: string; reason?: string; lock_version?: number }) => call<ItemRead>("POST", `${comp(o)}/items/${id}/status`, body);
export const signoffItem = (o: string, id: string, body: { decision: string; comments: string }) => call<{ item: ItemRead; review: ItemReviewRead }>("POST", `${comp(o)}/items/${id}/signoff`, body);
export const acknowledgeChange = (o: string, id: string, note: string) => call<ItemRead>("POST", `${comp(o)}/items/${id}/acknowledge-source-change`, { note });
export const reopenItem = (o: string, id: string, reason: string) => call<ItemRead>("POST", `${comp(o)}/items/${id}/reopen`, { reason });

// ------------------------------------------------------------------------------------ tasks and evidence
export async function fetchTasks(o: string, params: { updated_since?: string; limit?: number; offset?: number } = {}): Promise<Page<TaskRead>> {
  const r = await call<{ tasks: TaskRead[]; total: number; as_of: string; server_time: string }>("GET", `${comp(o)}/tasks${qs({ limit: 1000, ...params })}`);
  return { rows: r.tasks, total: r.total, as_of: r.as_of, server_time: r.server_time };
}
export const createTask = (o: string, body: { compliance_item_id: string; title: string; description?: string | null; assigned_to_user_id?: string | null; due_date: string; priority: string }) =>
  call<{ task: TaskRead; item: ItemRead }>("POST", `${comp(o)}/tasks`, body);
export const patchTask = (o: string, id: string, body: Record<string, unknown>) => call<{ task: TaskRead; item: ItemRead }>("PATCH", `${comp(o)}/tasks/${id}`, body);
export const cancelTask = (o: string, id: string, reason: string) => call<{ task: TaskRead; item: ItemRead }>("POST", `${comp(o)}/tasks/${id}/cancel`, { reason });
export const reviewTask = (o: string, id: string, body: { decision: string; comments: string }) =>
  call<{ review: TaskReviewRead; task: TaskRead; item: ItemRead }>("POST", `${comp(o)}/tasks/${id}/reviews`, body);
export const withdrawEvidence = (o: string, taskId: string, evidenceId: string, reason: string) =>
  call<{ evidence: EvidenceRead; task: TaskRead; item: ItemRead }>("POST", `${comp(o)}/tasks/${taskId}/evidence/${evidenceId}/withdraw`, { reason });

export interface EvidenceUploadResult {
  evidence: EvidenceRead;
  task: TaskRead;
  item: ItemRead;
}

/** Uploads one evidence file with progress (fetch cannot report upload progress). */
export function uploadEvidence(o: string, taskId: string, file: File, notes: string, onProgress: (fraction: number) => void): { promise: Promise<EvidenceUploadResult>; abort: () => void } {
  const xhr = new XMLHttpRequest();
  const promise = new Promise<EvidenceUploadResult>((resolve, reject) => {
    xhr.open("POST", `${getApiBaseUrl()}${comp(o)}/tasks/${taskId}/evidence`);
    const token = getAuthToken();
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(e.loaded / e.total);
    };
    xhr.onload = () => {
      let body: any = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        body = null;
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body);
      else reject(new WorkspaceError(xhr.status, messageFrom(body, xhr.status), body?.current));
    };
    xhr.onerror = () => reject(new WorkspaceError(0, `Cannot reach the RegWatch API at ${getApiBaseUrl()}. Check that the backend is running.`));
    xhr.onabort = () => reject(new WorkspaceError(0, "Upload cancelled."));
    const form = new FormData();
    form.append("file", file);
    if (notes.trim()) form.append("notes", notes.trim());
    xhr.send(form);
  });
  return { promise, abort: () => xhr.abort() };
}

async function saveBlob(res: Response, fallbackName: string) {
  const blob = await res.blob();
  let name = fallbackName;
  const cd = res.headers.get("content-disposition") || "";
  const star = /filename\*=UTF-8''([^;]+)/i.exec(cd);
  if (star) {
    try {
      name = decodeURIComponent(star[1]);
    } catch {
      /* keep fallback */
    }
  }
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Downloads an evidence file with the sign-in token, then saves it through a temporary link. */
export async function downloadEvidence(o: string, taskId: string, evidenceId: string, fallbackName: string): Promise<void> {
  const res = await apiFetch(`${comp(o)}/tasks/${taskId}/evidence/${evidenceId}/download`, { cache: "no-store" });
  if (!res.ok) await fail(res);
  await saveBlob(res, fallbackName);
}

// ------------------------------------------------------------------------------------ audit and report
export interface AuditPage {
  events: AuditRead[];
  next_before: string | null;
}
export const fetchAudit = (o: string, params: { entity_id?: string; entity_type?: string; actor_id?: string; action?: string; before?: string; limit?: number }) =>
  call<AuditPage>("GET", `${comp(o)}/audit${qs(params)}`);
export const fetchReport = (o: string, registerId?: string | null) => call<ReportData>("GET", `${comp(o)}/report${qs({ register_id: registerId || undefined })}`);
export async function downloadReportCsv(o: string, registerId?: string | null): Promise<void> {
  const res = await apiFetch(`${comp(o)}/report${qs({ format: "csv", register_id: registerId || undefined })}`, { cache: "no-store" });
  if (!res.ok) await fail(res);
  await saveBlob(res, "regwatch-report.csv");
}
