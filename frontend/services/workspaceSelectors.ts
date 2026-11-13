"use client";

/** Lists and counts worked out from the shared store (see workspaceStore.ts). */
import type { ItemRead, TaskRead } from "./workspaceApi";
import { canReviewTaskRole, canSignOffRole, signoffBlock, summarize, taskReviewBlock, type DashboardData } from "./workspaceRules";
import { WorkspaceState, meOf, orgItems, orgTasks, departmentsOf } from "./workspaceStore";

const cache = new Map<string, { deps: unknown[]; value: any }>();
function memo<T>(key: string, deps: unknown[], compute: () => T): T {
  const hit = cache.get(key);
  if (hit && hit.deps.length === deps.length && hit.deps.every((d, i) => d === deps[i])) return hit.value as T;
  const value = compute();
  cache.set(key, { deps, value });
  return value;
}

export interface ReviewLists {
  tasks: { task: TaskRead; item: ItemRead }[];
  tasksBlocked: { task: TaskRead; item: ItemRead }[];
  items: ItemRead[];
  itemsBlocked: ItemRead[];
}

/** What waits for this user: evidence to review and items to sign off, and what they cannot decide themselves. */
export function reviewLists(s: WorkspaceState, orgId: string): ReviewLists {
  const me = meOf(s, orgId);
  const items = orgItems(s, orgId);
  const tasks = orgTasks(s, orgId);
  return memo(`review:${orgId}`, [me, items, tasks], () => {
    const out: ReviewLists = { tasks: [], tasksBlocked: [], items: [], itemsBlocked: [] };
    if (!me) return out;
    const byId: Record<string, ItemRead> = {};
    items.forEach((i) => (byId[i.id] = i));
    for (const t of tasks) {
      if (t.status !== "SUBMITTED") continue;
      const item = byId[t.compliance_item_id];
      if (!item || !canReviewTaskRole(me, item)) continue;
      (taskReviewBlock(me, t) ? out.tasksBlocked : out.tasks).push({ task: t, item });
    }
    if (canSignOffRole(me)) {
      for (const item of items) {
        if (item.status !== "EVIDENCE_SUBMITTED") continue;
        const its = tasks.filter((t) => t.compliance_item_id === item.id);
        (signoffBlock(me, item, its) ? out.itemsBlocked : out.items).push(item);
      }
    }
    return out;
  });
}

export function reviewCounts(s: WorkspaceState, orgId: string) {
  const l = reviewLists(s, orgId);
  return { tasks: l.tasks.length, items: l.items.length, total: l.tasks.length + l.items.length };
}

export function selectDashboard(s: WorkspaceState, orgId: string): DashboardData {
  const items = orgItems(s, orgId);
  const tasks = orgTasks(s, orgId);
  const departments = departmentsOf(s, orgId);
  return memo(`dash:${orgId}`, [items, tasks, departments, s.today], () => summarize(items, tasks, departments, s.today));
}
