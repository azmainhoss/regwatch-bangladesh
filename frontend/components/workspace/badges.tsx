"use client";

import { Tag } from "../StatusBadge";
import { ITEM_STATUS_LABEL, ITEM_STATUS_TONE, TASK_STATUS_LABEL, TASK_STATUS_TONE } from "@/services/workspaceRules";
import { ROLE_LABEL } from "@/services/workspaceApi";

/** The status of an item as people read it: "Overdue" wins over the stored status when the deadline has passed. */
export function ItemStatusBadge({ status }: { status: string }) {
  return (
    <span data-testid="item-status" data-status={status}>
      <Tag tone={ITEM_STATUS_TONE[status] ?? "muted"}>{ITEM_STATUS_LABEL[status] ?? status}</Tag>
    </span>
  );
}

export function TaskStatusBadge({ status }: { status: string }) {
  return (
    <span data-testid="task-status" data-status={status}>
      <Tag tone={TASK_STATUS_TONE[status] ?? "muted"}>{TASK_STATUS_LABEL[status] ?? status}</Tag>
    </span>
  );
}

const PRIORITY_TONE: Record<string, "muted" | "info" | "warn" | "bad"> = { LOW: "muted", MEDIUM: "info", HIGH: "warn", CRITICAL: "bad" };

export function PriorityTag({ priority }: { priority: string }) {
  return <Tag tone={PRIORITY_TONE[priority] ?? "muted"}>{priority.charAt(0) + priority.slice(1).toLowerCase()}</Tag>;
}

export function RoleTag({ role }: { role: string }) {
  return <Tag tone="accent">{ROLE_LABEL[role] ?? role}</Tag>;
}
