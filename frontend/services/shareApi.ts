"use client";

import { apiFetch, ApiError } from "./api";

async function json<T>(res: Response, fallback: string): Promise<T> {
  if (!res.ok) {
    let msg = fallback;
    try {
      const b = await res.json();
      if (typeof b?.detail === "string") msg = b.detail;
      else if (Array.isArray(b?.detail)) msg = "Check the email addresses.";
    } catch {
      /* keep */
    }
    throw new ApiError(res.status, msg);
  }
  return res.json();
}

export interface TeamMember {
  user_id: string;
  name: string;
  email: string;
  organization_id: string;
  organization_name: string;
}

export interface Assignment {
  id: string;
  document_id: string;
  reference_number?: string | null;
  title: string;
  publication_date?: string | null;
  assigned_by_user_id: string;
  assignee_user_id: string;
  assigned_by_name: string;
  assignee_name: string;
  note?: string | null;
  due_date?: string | null;
  status: "OPEN" | "DONE";
  email_status?: "SENT" | "OFF" | "FAILED" | null;
  created_at: string;
}

const post = (path: string, body: unknown) =>
  apiFetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export async function fetchTeam(): Promise<TeamMember[]> {
  return json(await apiFetch("/share/team", { cache: "no-store" }), "Could not load your team.");
}

export interface EmailBody {
  document_id: string;
  to: string[];
  note?: string;
  mind_map_png?: string | null;
  attach_pdf?: boolean;
}

export async function sendEmail(body: EmailBody): Promise<{ sent: number; message: string }> {
  return json(await post("/share/email", body), "The email could not be sent.");
}

/** Downloads the email as a file that opens as a ready draft in Outlook or Apple Mail. */
export async function downloadEmailFile(body: EmailBody, filename: string): Promise<void> {
  const res = await post("/share/email/file", body);
  if (!res.ok) await json(res, "Could not make the email.");
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 5000);
}

export async function assign(body: {
  document_id: string;
  assignee_user_ids: string[];
  note?: string;
  due_date?: string | null;
  send_email?: boolean;
  mind_map_png?: string | null;
}): Promise<{ created: number; emailed: number; email_off: boolean; assignments: Assignment[] }> {
  return json(await post("/share/assign", body), "Could not assign the circular.");
}

export async function fetchAssignments(scope: "mine" | "by_me" | "all" = "all"): Promise<Assignment[]> {
  return json(await apiFetch(`/share/assignments?scope=${scope}`, { cache: "no-store" }), "Could not load assignments.");
}

export async function setAssignmentStatus(id: string, status: "OPEN" | "DONE"): Promise<Assignment> {
  return json(
    await apiFetch(`/share/assignments/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }) }),
    "Could not save that change.",
  );
}
