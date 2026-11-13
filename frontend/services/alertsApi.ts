/**
 * Calls for alerts. Types match backend/app/modules/alerts/schemas.py.
 */
import { ApiError, apiFetch } from "./api";

export type AlertSeverity = "info" | "warn" | "bad";
export type EmailMode = "OFF" | "INSTANT" | "DIGEST";

export interface AlertQuote {
  text: string;
  page_number: number | null;
  document_id: string | null;
  document_reference: string | null;
}

export interface AlertRead {
  id: string;
  kind: string;
  group: string;
  severity: AlertSeverity | string;
  organization_id: string | null;
  organization_name: string | null;
  title: string;
  body: string;
  detail: string | null;
  link: string;
  document: { id: string; reference_number: string | null; title: string } | null;
  quote: AlertQuote | null;
  read_at: string | null;
  created_at: string;
}

export interface AlertSummary {
  unread_count: number;
  latest_id: string | null;
  latest_created_at: string | null;
  email_configured: boolean;
  server_time: string;
}

export interface AlertList {
  alerts: AlertRead[];
  next_before: string | null;
  unread_count: number;
}

export interface ChannelSetting {
  in_app: boolean;
  email: EmailMode;
}

export interface PreferencesRead {
  channels: Record<string, ChannelSetting>;
  email_enabled: boolean;
  library_department_codes: string[];
  library_document_types: string[];
  library_keywords: string[];
  lock_version: number;
  email_configured: boolean;
  due_soon_days: number[];
  digest_time: string;
  options: {
    groups: Array<{ id: string; label: string; description: string }>;
    department_codes: Array<{ code: string; name: string }>;
    document_types: string[];
  };
}

export interface OutboxCounts {
  pending: number;
  sending: number;
  sent_24h: number;
  failed: number;
  expired: number;
}

export interface EmailStatus {
  configured: boolean;
  host: string | null;
  port: number | null;
  tls_mode: string;
  from_address: string | null;
  username_set: boolean;
  password_set: boolean;
  worker_running: boolean;
  outbox: OutboxCounts;
  last_error: string | null;
}

export interface OutboxRow {
  id: string;
  kind: string;
  status: string;
  attempts: number;
  next_attempt_at: string | null;
  sent_at: string | null;
  last_error: string | null;
  created_at: string;
  to_masked: string;
}

export interface TestEmailResult {
  ok: boolean;
  outcome: string;
  smtp_code: number | null;
  detail: string;
}

/** An API error that may carry the server's current copy (HTTP 409). */
export class AlertsApiError extends ApiError {
  current: any;
  constructor(status: number, message: string, current?: any) {
    super(status, message);
    this.current = current;
  }
}

function messageFrom(body: any, status: number): string {
  const d = body?.detail ?? body?.message;
  if (typeof d === "string" && d.trim()) return d;
  if (Array.isArray(d) && d.length > 0) return d.map((x: any) => x?.msg ?? "").filter(Boolean).join("; ");
  return `The request failed (HTTP ${status}).`;
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await apiFetch(path, init);
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new AlertsApiError(res.status, messageFrom(body, res.status), body?.current);
  }
  return (await res.json()) as T;
}

const JSON_HEADERS = { "Content-Type": "application/json" };

export const fetchSummary = () => call<AlertSummary>("/alerts/summary");

export function fetchAlerts(p: { filter?: "all" | "unread"; group?: string | null; before?: string | null; after?: string | null; limit?: number } = {}) {
  const q = new URLSearchParams();
  if (p.filter && p.filter !== "all") q.set("filter", p.filter);
  if (p.group) q.set("group", p.group);
  if (p.before) q.set("before", p.before);
  if (p.after) q.set("after", p.after);
  q.set("limit", String(p.limit ?? 30));
  return call<AlertList>(`/alerts?${q.toString()}`);
}

export const postRead = (id: string) => call<{ alert: AlertRead; unread_count: number }>(`/alerts/${id}/read`, { method: "POST" });
export const postUnread = (id: string) => call<{ alert: AlertRead; unread_count: number }>(`/alerts/${id}/unread`, { method: "POST" });
export const postReadAll = (upTo: string, group?: string | null) =>
  call<{ updated: number; unread_count: number }>("/alerts/read-all", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ up_to: upTo, group: group || undefined }),
  });

export const fetchPreferences = () => call<PreferencesRead>("/alerts/preferences");
export const putPreferences = (p: PreferencesRead) =>
  call<PreferencesRead>("/alerts/preferences", {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify({
      channels: p.channels,
      email_enabled: p.email_enabled,
      library_department_codes: p.library_department_codes,
      library_document_types: p.library_document_types,
      library_keywords: p.library_keywords,
      lock_version: p.lock_version,
    }),
  });

export const fetchEmailStatus = () => call<EmailStatus>("/alerts/admin/email-status");
export const postTestEmail = () => call<TestEmailResult>("/alerts/admin/test-email", { method: "POST" });
export const fetchOutbox = (limit = 20) => call<{ rows: OutboxRow[] }>(`/alerts/admin/outbox?limit=${limit}`);
export const postOutboxRetry = (id: string) => call<OutboxRow>(`/alerts/admin/outbox/${id}/retry`, { method: "POST" });
