"use client";

/**
 * One shared copy of everything the bank workspace shows. Every screen reads from here, so a change
 * made on one screen (a status, an assignee, a deadline, an evidence file, an approval) shows on all
 * of them in the same moment: register counts, the dashboard, the item screen, the review list, the
 * report, and the screen you go back to.
 *
 * - One record of each kind, by id. Lists are selectors over these maps.
 * - A change is shown first and saved in the background. Only the records it touched are put back, and
 *   only if nothing newer landed on them, when the save fails.
 * - A load never overwrites a record that is being saved or that is newer than the loaded copy.
 * - Other people and other tabs: a light refresh every 30 seconds, a full refresh on focus, and a
 *   message to other tabs after every save.
 */
import { useSyncExternalStore } from "react";
import { AUTH_CHANGED_EVENT, getStoredUser } from "./api";
import * as api from "./workspaceApi";
import type {
  AddableObligation,
  AuditRead,
  DepartmentRead,
  EvidenceRead,
  ItemRead,
  ItemReviewRead,
  MeInOrg,
  MemberRead,
  MyOrg,
  RegisterRead,
  Skipped,
  TaskRead,
  TaskReviewRead,
} from "./workspaceApi";
import {
  Me,
  checkEvidenceFile,
  daysLeft,
  dhakaToday,
  effectiveDeadline,
  isItemOverdue,
  isTaskOverdue,
  meFrom,
  msUntilDhakaMidnight,
} from "./workspaceRules";

// ------------------------------------------------------------------------------------ state
export interface UploadRow {
  id: string;
  orgId: string;
  taskId: string;
  itemId: string;
  fileName: string;
  size: number;
  progress: number;
  state: "uploading" | "error";
  error?: string;
}

export interface Notice {
  kind: "error" | "success" | "info";
  text: string;
}

export interface WorkspaceState {
  userId: string | null;
  orgs: MyOrg[] | null;
  orgsError: string | null;
  activeOrgId: string | null;
  me: Record<string, MeInOrg>;
  members: Record<string, MemberRead[]>;
  departments: Record<string, DepartmentRead[]>;
  registers: Record<string, RegisterRead>;
  items: Record<string, ItemRead>;
  tasks: Record<string, TaskRead>;
  evidence: Record<string, EvidenceRead>;
  taskReviews: Record<string, TaskReviewRead>;
  itemReviews: Record<string, ItemReviewRead>;
  history: Record<string, AuditRead[]>;
  historyNext: Record<string, string | null>;
  loaded: Record<string, "loading" | "ok" | { error: string }>;
  pending: Record<string, number>;
  lastSync: Record<string, { items?: string; tasks?: string }>;
  uploads: Record<string, UploadRow>;
  today: string;
  notice: Notice | null;
}

function emptyState(): WorkspaceState {
  return {
    userId: null,
    orgs: null,
    orgsError: null,
    activeOrgId: null,
    me: {},
    members: {},
    departments: {},
    registers: {},
    items: {},
    tasks: {},
    evidence: {},
    taskReviews: {},
    itemReviews: {},
    history: {},
    historyNext: {},
    loaded: {},
    pending: {},
    lastSync: {},
    uploads: {},
    today: dhakaToday(),
    notice: null,
  };
}

let state: WorkspaceState = emptyState();
const listeners = new Set<() => void>();
let noticeTimer: ReturnType<typeof setTimeout> | null = null;

function commit(next: Partial<WorkspaceState>) {
  state = { ...state, ...next };
  listeners.forEach((l) => l());
}

function subscribe(l: () => void) {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
}

export function getWorkspaceState() {
  return state;
}

export function useWorkspace(): WorkspaceState {
  return useSyncExternalStore(subscribe, getWorkspaceState, getWorkspaceState);
}

export function setNotice(notice: Notice | null) {
  if (noticeTimer) clearTimeout(noticeTimer);
  commit({ notice });
  if (notice && notice.kind !== "error") noticeTimer = setTimeout(() => commit({ notice: null }), 4500);
}
export const clearNotice = () => setNotice(null);

// ------------------------------------------------------------------------------------ derived fields
function normItem(item: ItemRead, today: string = state.today): ItemRead {
  const eff = effectiveDeadline(item);
  const overdue = isItemOverdue(item, today);
  const days = daysLeft(eff, today);
  if (item.effective_deadline === eff && item.is_overdue === overdue && item.days_left === days && item.display_status === (overdue ? "OVERDUE" : item.status)) return item;
  return { ...item, effective_deadline: eff, is_overdue: overdue, days_left: days, display_status: overdue ? "OVERDUE" : item.status };
}

function normTask(task: TaskRead, today: string = state.today): TaskRead {
  const overdue = isTaskOverdue(task, today);
  const days = daysLeft(task.due_date, today);
  if (task.is_overdue === overdue && task.days_left === days) return task;
  return { ...task, is_overdue: overdue, days_left: days };
}

function countsFor(itemId: string, tasks: Record<string, TaskRead>) {
  const c = { total: 0, open: 0, submitted: 0, approved: 0, overdue: 0 };
  let evidence = 0;
  for (const t of Object.values(tasks)) {
    if (t.compliance_item_id !== itemId) continue;
    evidence += t.evidence_count;
    if (t.status === "CANCELLED") continue;
    c.total++;
    if (t.status === "PENDING" || t.status === "IN_PROGRESS" || t.status === "REJECTED") c.open++;
    else if (t.status === "SUBMITTED") c.submitted++;
    else if (t.status === "APPROVED") c.approved++;
    if (t.is_overdue) c.overdue++;
  }
  return { counts: c, evidence };
}

/** Rebuilds the task and evidence counts of items from the tasks in the store. */
function recount(items: Record<string, ItemRead>, tasks: Record<string, TaskRead>, ids?: string[]): Record<string, ItemRead> {
  const next = { ...items };
  const keys = ids ?? Object.keys(items);
  let changed = false;
  // Group once for the full pass.
  const groups: Record<string, TaskRead[]> = {};
  if (!ids) for (const t of Object.values(tasks)) (groups[t.compliance_item_id] ||= []).push(t);
  for (const id of keys) {
    const it = next[id];
    if (!it) continue;
    const list = ids ? undefined : groups[id] || [];
    const { counts, evidence } = list ? countsFromList(list) : countsFor(id, tasks);
    const a = it.task_counts;
    if (a.total === counts.total && a.open === counts.open && a.submitted === counts.submitted && a.approved === counts.approved && a.overdue === counts.overdue && it.evidence_count === evidence) continue;
    next[id] = { ...it, task_counts: counts, evidence_count: evidence };
    changed = true;
  }
  return changed ? next : items;
}

function countsFromList(list: TaskRead[]) {
  const c = { total: 0, open: 0, submitted: 0, approved: 0, overdue: 0 };
  let evidence = 0;
  for (const t of list) {
    evidence += t.evidence_count;
    if (t.status === "CANCELLED") continue;
    c.total++;
    if (t.status === "PENDING" || t.status === "IN_PROGRESS" || t.status === "REJECTED") c.open++;
    else if (t.status === "SUBMITTED") c.submitted++;
    else if (t.status === "APPROVED") c.approved++;
    if (t.is_overdue) c.overdue++;
  }
  return { counts: c, evidence };
}

function tasksLoaded(orgId: string) {
  return state.loaded[`tasks:${orgId}`] === "ok";
}

// ------------------------------------------------------------------------------------ writing records
function sameRecord(a: any, b: any) {
  return a === b || JSON.stringify(a) === JSON.stringify(b);
}

/** Puts server copies of items into the store, skipping records that are being saved or are newer here. */
function mergeItems(list: ItemRead[]) {
  if (!list.length) return;
  const items = { ...state.items };
  let changed = false;
  for (const raw of list) {
    const cur = items[raw.id];
    if (cur && ((state.pending[raw.id] ?? 0) > 0 || cur.lock_version > raw.lock_version)) continue;
    const next = normItem(raw);
    if (cur && cur.lock_version === next.lock_version && sameRecord({ ...cur, task_counts: 0, evidence_count: 0 }, { ...next, task_counts: 0, evidence_count: 0 })) continue;
    items[raw.id] = next;
    changed = true;
  }
  if (!changed) return;
  const orgId = list[0].organization_id;
  commit({ items: tasksLoaded(orgId) ? recount(items, state.tasks) : items });
}

/** Puts items fetched by another screen (the report) into the shared store. */
export function seedItems(list: ItemRead[]) {
  mergeItems(list);
}

function mergeTasks(list: TaskRead[]) {
  if (!list.length) return;
  const tasks = { ...state.tasks };
  let changed = false;
  for (const raw of list) {
    const cur = tasks[raw.id];
    if (cur && ((state.pending[raw.id] ?? 0) > 0 || cur.lock_version > raw.lock_version)) continue;
    const next = normTask(raw);
    if (cur && cur.lock_version === next.lock_version && sameRecord(cur, next)) continue;
    tasks[raw.id] = next;
    changed = true;
  }
  if (!changed) return;
  const orgId = list[0].organization_id;
  const touched = Array.from(new Set(list.map((t) => t.compliance_item_id)));
  commit({ tasks, items: tasksLoaded(orgId) ? recount(state.items, tasks, touched) : state.items });
}

/**
 * Writes a server answer (task, item, evidence, reviews) over what is stored: a save just finished.
 * A record with another save still in flight is left alone; that save's answer replaces it next.
 */
function putServer(result: { task?: TaskRead; item?: ItemRead; evidence?: EvidenceRead; taskReview?: TaskReviewRead; itemReview?: ItemReviewRead }) {
  const next: Partial<WorkspaceState> = {};
  const busy = (id: string) => (state.pending[id] ?? 0) > 0;
  if (result.task && !(busy(result.task.id) && state.tasks[result.task.id])) next.tasks = { ...state.tasks, [result.task.id]: normTask(result.task) };
  if (result.item && !(busy(result.item.id) && state.items[result.item.id])) next.items = { ...state.items, [result.item.id]: normItem(result.item) };
  if (result.evidence) next.evidence = { ...state.evidence, [result.evidence.id]: result.evidence };
  if (result.taskReview) next.taskReviews = { ...state.taskReviews, [result.taskReview.id]: result.taskReview };
  if (result.itemReview) next.itemReviews = { ...state.itemReviews, [result.itemReview.id]: result.itemReview };
  if (result.task && tasksLoaded(result.task.organization_id)) {
    next.items = recount(next.items ?? state.items, next.tasks ?? state.tasks, [result.task.compliance_item_id]);
  }
  commit(next);
}

function setItemLocal(id: string, change: Partial<ItemRead>, bump = true) {
  const cur = state.items[id];
  if (!cur) return;
  const next = normItem({ ...cur, ...change, lock_version: bump ? cur.lock_version + 1 : cur.lock_version });
  commit({ items: { ...state.items, [id]: next } });
}

function setTaskLocal(id: string, change: Partial<TaskRead>, bump = true) {
  const cur = state.tasks[id];
  if (!cur) return;
  const next = normTask({ ...cur, ...change, lock_version: bump ? cur.lock_version + 1 : cur.lock_version });
  const tasks = { ...state.tasks, [id]: next };
  commit({ tasks, items: tasksLoaded(next.organization_id) ? recount(state.items, tasks, [next.compliance_item_id]) : state.items });
}

function renormalizeAll(today: string) {
  const items: Record<string, ItemRead> = {};
  for (const [id, it] of Object.entries(state.items)) items[id] = normItem(it, today);
  const tasks: Record<string, TaskRead> = {};
  for (const [id, t] of Object.entries(state.tasks)) tasks[id] = normTask(t, today);
  commit({ today, items, tasks });
}

// ------------------------------------------------------------------------------------ the day clock
let clockStarted = false;
function startClock() {
  if (clockStarted || typeof window === "undefined") return;
  clockStarted = true;
  const tick = () => {
    renormalizeAll(dhakaToday());
    setTimeout(tick, msUntilDhakaMidnight());
  };
  setTimeout(tick, msUntilDhakaMidnight());
  // A sleeping laptop may wake long after midnight: check the date when the tab comes back.
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && dhakaToday() !== state.today) renormalizeAll(dhakaToday());
  });
}

// ------------------------------------------------------------------------------------ other tabs
const CHANNEL = "regwatch-workspace";
let channel: BroadcastChannel | null = null;
function getChannel() {
  if (channel || typeof window === "undefined" || typeof BroadcastChannel === "undefined") return channel;
  channel = new BroadcastChannel(CHANNEL);
  channel.onmessage = (e) => {
    const orgId = e.data?.orgId;
    if (orgId && orgId === state.activeOrgId) void refreshWorkspace(orgId, false);
  };
  return channel;
}
function tellOtherTabs(orgId: string) {
  try {
    getChannel()?.postMessage({ orgId });
  } catch {
    /* other tabs just refresh on their own timer */
  }
}

// ------------------------------------------------------------------------------------ session
let sessionBound = false;
function bindSession() {
  if (sessionBound || typeof window === "undefined") return;
  sessionBound = true;
  getChannel();
  startClock();
  window.addEventListener(AUTH_CHANGED_EVENT, () => syncSessionUser());
}

/** A different person signing in must never see the previous person's bank data. */
export function syncSessionUser() {
  const id = getStoredUser()?.id ?? null;
  if (state.userId !== id) {
    inflight.clear();
    state = { ...emptyState(), userId: id };
    listeners.forEach((l) => l());
  }
}

// ------------------------------------------------------------------------------------ loading
const inflight = new Map<string, Promise<void>>();
function once(key: string, run: () => Promise<void>): Promise<void> {
  const existing = inflight.get(key);
  if (existing) return existing;
  const p = run().finally(() => inflight.delete(key));
  inflight.set(key, p);
  return p;
}

function setLoaded(key: string, value: "loading" | "ok" | { error: string }) {
  commit({ loaded: { ...state.loaded, [key]: value } });
}

function errText(e: unknown, fallback: string): string {
  return (e as any)?.message || fallback;
}

export function loadOrgs(force = false): Promise<void> {
  bindSession();
  syncSessionUser();
  return once("orgs", async () => {
    if (!force && state.orgs) return;
    try {
      const orgs = await api.fetchMyOrgs();
      commit({ orgs, orgsError: null });
    } catch (e) {
      commit({ orgsError: errText(e, "Could not load your workspaces.") });
    }
  });
}

async function loadList<T>(key: string, fetcher: () => Promise<T>, store: (data: T) => void, force: boolean): Promise<void> {
  return once(key, async () => {
    if (!force && state.loaded[key] === "ok") return;
    if (state.loaded[key] !== "ok") setLoaded(key, "loading");
    try {
      store(await fetcher());
      setLoaded(key, "ok");
    } catch (e) {
      if (state.loaded[key] !== "ok") setLoaded(key, { error: errText(e, "Could not load this list.") });
    }
  });
}

export const loadMe = (o: string, force = false) => loadList(`me:${o}`, () => api.fetchMe(o), (me) => commit({ me: { ...state.me, [o]: me } }), force);
export const loadMembers = (o: string, force = false) => loadList(`members:${o}`, () => api.fetchMembers(o), (m) => commit({ members: { ...state.members, [o]: m } }), force);
export const loadDepartments = (o: string, force = false) => loadList(`departments:${o}`, () => api.fetchDepartments(o), (d) => commit({ departments: { ...state.departments, [o]: d } }), force);
export const loadRegisters = (o: string, force = false) =>
  loadList(
    `registers:${o}`,
    () => api.fetchRegisters(o),
    (list) => {
      const registers = { ...state.registers };
      for (const id of Object.keys(registers)) if (registers[id].organization_id === o && !id.startsWith("tmp:") && !list.some((r) => r.id === id)) delete registers[id];
      for (const r of list) {
        if ((state.pending[r.id] ?? 0) > 0) continue;
        registers[r.id] = r;
      }
      commit({ registers });
    },
    force
  );

export const loadItems = (o: string, force = false) =>
  loadList(
    `items:${o}`,
    async () => {
      const first = await api.fetchItems(o, { limit: 500, offset: 0 });
      let rows = first.rows;
      while (rows.length < first.total) {
        const more = await api.fetchItems(o, { limit: 500, offset: rows.length });
        if (!more.rows.length) break;
        rows = rows.concat(more.rows);
      }
      return { rows, at: first.server_time };
    },
    ({ rows, at }) => {
      mergeItems(rows);
      commit({ lastSync: { ...state.lastSync, [o]: { ...state.lastSync[o], items: at } } });
    },
    force
  );

export const loadTasks = (o: string, force = false) =>
  loadList(
    `tasks:${o}`,
    async () => {
      const first = await api.fetchTasks(o, { limit: 1000, offset: 0 });
      let rows = first.rows;
      while (rows.length < first.total) {
        const more = await api.fetchTasks(o, { limit: 1000, offset: rows.length });
        if (!more.rows.length) break;
        rows = rows.concat(more.rows);
      }
      return { rows, at: first.server_time };
    },
    ({ rows, at }) => {
      mergeTasks(rows);
      // Counts on items come from tasks once all of them are here.
      commit({ lastSync: { ...state.lastSync, [o]: { ...state.lastSync[o], tasks: at } } });
      commit({ items: recount(state.items, state.tasks) });
    },
    force
  );

/** Opens a workspace: loads everything the screens need, in parallel, so every list opens at once. */
export function ensureWorkspace(orgId: string): Promise<void> {
  bindSession();
  syncSessionUser();
  if (state.activeOrgId !== orgId) commit({ activeOrgId: orgId });
  return Promise.all([loadMe(orgId), loadMembers(orgId), loadDepartments(orgId), loadRegisters(orgId), loadItems(orgId), loadTasks(orgId)]).then(() => undefined);
}

/** Refreshes from the server. `full` also refetches every item and task (used on focus); otherwise only what changed. */
export async function refreshWorkspace(orgId: string, full: boolean): Promise<void> {
  if (state.loaded[`items:${orgId}`] !== "ok") return;
  await once(`refresh:${orgId}:${full}`, async () => {
    try {
      if (full) {
        await Promise.all([loadItems(orgId, true), loadTasks(orgId, true), loadRegisters(orgId, true), loadMembers(orgId, true), loadDepartments(orgId, true)]);
        return;
      }
      const sync = state.lastSync[orgId] || {};
      const [items, tasks] = await Promise.all([
        api.fetchItems(orgId, { updated_since: sync.items, limit: 500 }),
        api.fetchTasks(orgId, { updated_since: sync.tasks, limit: 1000 }),
      ]);
      mergeItems(items.rows);
      mergeTasks(tasks.rows);
      commit({ lastSync: { ...state.lastSync, [orgId]: { items: items.server_time, tasks: tasks.server_time } } });
      await loadRegisters(orgId, true);
    } catch {
      /* the next refresh tries again; the screen keeps what it has */
    }
  });
}

/** Starts the 30-second refresh and the refresh on focus for the open workspace. Returns a stop function. */
export function startSync(orgId: string): () => void {
  const timer = setInterval(() => {
    if (!document.hidden) void refreshWorkspace(orgId, false);
  }, 30000);
  const onFocus = () => void refreshWorkspace(orgId, true);
  window.addEventListener("focus", onFocus);
  const onVisible = () => {
    if (!document.hidden) onFocus();
  };
  document.addEventListener("visibilitychange", onVisible);
  return () => {
    clearInterval(timer);
    window.removeEventListener("focus", onFocus);
    document.removeEventListener("visibilitychange", onVisible);
  };
}

/** The item screen: the item, its tasks, evidence, reviews and history, fetched fresh (cheap, and it makes the circular-change flag current). */
export function loadItemDetail(orgId: string, itemId: string): Promise<void> {
  return once(`detail:${itemId}`, async () => {
    const key = `detail:${itemId}`;
    if (state.loaded[key] !== "ok") setLoaded(key, "loading");
    try {
      const d = await api.fetchItemDetail(orgId, itemId);
      mergeItems([d.item]);
      mergeTasks(d.tasks);
      const evidence = { ...state.evidence };
      for (const e of d.evidence) evidence[e.id] = e;
      const taskReviews = { ...state.taskReviews };
      for (const r of d.task_reviews) taskReviews[r.id] = r;
      const itemReviews = { ...state.itemReviews };
      for (const r of d.item_reviews) itemReviews[r.id] = r;
      commit({ evidence, taskReviews, itemReviews });
      setLoaded(key, "ok");
    } catch (e: any) {
      setLoaded(key, { error: e?.status === 404 ? "NOT_FOUND" : errText(e, "Could not load this item.") });
    }
  });
}

export function loadHistory(orgId: string, itemId: string, more = false): Promise<void> {
  return once(`history:${itemId}:${more}`, async () => {
    const before = more ? state.historyNext[itemId] ?? undefined : undefined;
    if (more && !before) return;
    try {
      const page = await api.fetchAudit(orgId, { entity_id: itemId, limit: 20, before });
      const current = state.history[itemId] ?? [];
      // Notes for saves still in flight stay on top until their save answers.
      const inFlight = current.filter((e) => e.id.startsWith("tmp:"));
      const kept = more ? current.filter((e) => !e.id.startsWith("tmp:")) : [];
      const seen = new Set<string>();
      const merged = [...kept, ...page.events].filter((e) => (seen.has(e.id) ? false : (seen.add(e.id), true)));
      commit({
        history: { ...state.history, [itemId]: [...inFlight, ...merged] },
        historyNext: { ...state.historyNext, [itemId]: page.next_before },
      });
    } catch {
      /* the list keeps what it has */
    }
  });
}

// ------------------------------------------------------------------------------------ selectors
const selCache = new Map<string, { deps: unknown[]; value: any }>();
function memo<T>(key: string, deps: unknown[], compute: () => T): T {
  const hit = selCache.get(key);
  if (hit && hit.deps.length === deps.length && hit.deps.every((d, i) => d === deps[i])) return hit.value as T;
  const value = compute();
  selCache.set(key, { deps, value });
  return value;
}

export function orgItems(s: WorkspaceState, orgId: string): ItemRead[] {
  return memo(`items:${orgId}`, [s.items], () =>
    Object.values(s.items)
      .filter((i) => i.organization_id === orgId)
      .sort((a, b) => (a.created_at === b.created_at ? (a.id < b.id ? -1 : 1) : a.created_at < b.created_at ? -1 : 1))
  );
}

export function orgTasks(s: WorkspaceState, orgId: string): TaskRead[] {
  return memo(`tasks:${orgId}`, [s.tasks], () =>
    Object.values(s.tasks)
      .filter((t) => t.organization_id === orgId)
      .sort((a, b) => (a.due_date === b.due_date ? (a.id < b.id ? -1 : 1) : a.due_date < b.due_date ? -1 : 1))
  );
}

export function orgRegisters(s: WorkspaceState, orgId: string, includeArchived = false): RegisterRead[] {
  return memo(`registers:${orgId}:${includeArchived}`, [s.registers], () =>
    Object.values(s.registers)
      .filter((r) => r.organization_id === orgId && (includeArchived || r.is_active))
      .sort((a, b) => a.title.localeCompare(b.title))
  );
}

export function registerItems(s: WorkspaceState, orgId: string, registerId: string): ItemRead[] {
  return memo(`regitems:${registerId}`, [orgItems(s, orgId)], () => orgItems(s, orgId).filter((i) => i.register_id === registerId));
}

export function itemTasks(s: WorkspaceState, orgId: string, itemId: string): TaskRead[] {
  return memo(`itemtasks:${itemId}`, [orgTasks(s, orgId)], () => orgTasks(s, orgId).filter((t) => t.compliance_item_id === itemId));
}

export function taskEvidence(s: WorkspaceState, taskId: string): EvidenceRead[] {
  return memo(`ev:${taskId}`, [s.evidence], () =>
    Object.values(s.evidence)
      .filter((e) => e.task_id === taskId)
      .sort((a, b) => (a.created_at < b.created_at ? -1 : 1))
  );
}

export function taskReviewsOf(s: WorkspaceState, taskId: string): TaskReviewRead[] {
  return memo(`tr:${taskId}`, [s.taskReviews], () =>
    Object.values(s.taskReviews)
      .filter((r) => r.task_id === taskId)
      .sort((a, b) => (a.created_at < b.created_at ? 1 : -1))
  );
}

export function itemReviewsOf(s: WorkspaceState, itemId: string): ItemReviewRead[] {
  return memo(`ir:${itemId}`, [s.itemReviews], () =>
    Object.values(s.itemReviews)
      .filter((r) => r.item_id === itemId)
      .sort((a, b) => (a.created_at < b.created_at ? 1 : -1))
  );
}

export function itemEvidence(s: WorkspaceState, orgId: string, itemId: string): EvidenceRead[] {
  const taskIds = new Set(itemTasks(s, orgId, itemId).map((t) => t.id));
  return memo(`itemev:${itemId}`, [s.evidence, orgTasks(s, orgId)], () => Object.values(s.evidence).filter((e) => taskIds.has(e.task_id)));
}

export function meOf(s: WorkspaceState, orgId: string): Me | null {
  const m = s.me[orgId];
  return m ? memo(`me:${orgId}`, [m], () => meFrom(m.membership)) : null;
}

const NO_DEPARTMENTS: DepartmentRead[] = [];
const NO_MEMBERS: MemberRead[] = [];
export function departmentsOf(s: WorkspaceState, orgId: string): DepartmentRead[] {
  return s.departments[orgId] ?? NO_DEPARTMENTS;
}
export function membersOf(s: WorkspaceState, orgId: string): MemberRead[] {
  return s.members[orgId] ?? NO_MEMBERS;
}

export function userName(s: WorkspaceState, orgId: string, userId: string | null | undefined): string {
  if (!userId) return "no one";
  const m = (s.members[orgId] || []).find((x) => x.user.id === userId);
  return m ? m.user.full_name : "someone";
}

export function isPending(s: WorkspaceState, id: string): boolean {
  return (s.pending[id] ?? 0) > 0 || id.startsWith("tmp:");
}

// ------------------------------------------------------------------------------------ saving changes
interface Plan<R> {
  orgId: string;
  items?: string[];
  tasks?: string[];
  registers?: string[];
  /** Shows the change at once. */
  optimistic: () => void;
  request: () => Promise<R>;
  /** Writes the server's answer. */
  done: (r: R) => void;
  success?: string;
  failure: string;
  onConflict?: (current: any) => void;
  history?: { itemId: string; action: string; entity_type: string; entity_id: string; before?: any; after?: any };
}

function bumpPending(ids: string[], by: number) {
  const pending = { ...state.pending };
  for (const id of ids) pending[id] = Math.max(0, (pending[id] ?? 0) + by);
  commit({ pending });
}

function currentActor() {
  const u = getStoredUser();
  return u ? { id: u.id, full_name: u.full_name, email: u.email } : null;
}

function pushHistory(h: NonNullable<Plan<unknown>["history"]>) {
  const entry: AuditRead = {
    id: `tmp:${Math.random().toString(36).slice(2)}`,
    action: h.action,
    entity_type: h.entity_type,
    entity_id: h.entity_id,
    actor: currentActor(),
    before: h.before ?? null,
    after: h.after ?? null,
    created_at: new Date().toISOString(),
  };
  commit({ history: { ...state.history, [h.itemId]: [entry, ...(state.history[h.itemId] ?? [])] } });
  return entry.id;
}

function dropHistory(itemId: string, entryId: string) {
  commit({ history: { ...state.history, [itemId]: (state.history[itemId] ?? []).filter((e) => e.id !== entryId) } });
}

/** Shows a change, saves it, and puts back only what this change touched if the save fails. */
async function mutate<R>(plan: Plan<R>): Promise<R | null> {
  const itemIds = plan.items ?? [];
  const taskIds = plan.tasks ?? [];
  const regIds = plan.registers ?? [];
  const beforeItems: Record<string, ItemRead | undefined> = {};
  const beforeTasks: Record<string, TaskRead | undefined> = {};
  const beforeRegs: Record<string, RegisterRead | undefined> = {};
  itemIds.forEach((id) => (beforeItems[id] = state.items[id]));
  taskIds.forEach((id) => (beforeTasks[id] = state.tasks[id]));
  regIds.forEach((id) => (beforeRegs[id] = state.registers[id]));

  plan.optimistic();
  const optLock: Record<string, number | undefined> = {};
  itemIds.forEach((id) => (optLock[id] = state.items[id]?.lock_version));
  taskIds.forEach((id) => (optLock[id] = state.tasks[id]?.lock_version));
  const histId = plan.history ? pushHistory(plan.history) : null;
  const all = [...itemIds, ...taskIds, ...regIds];
  bumpPending(all, 1);
  try {
    const result = await plan.request();
    bumpPending(all, -1);
    plan.done(result);
    if (histId && plan.history) dropHistory(plan.history.itemId, histId);
    if (plan.history) void loadHistory(plan.orgId, plan.history.itemId);
    if (plan.success) setNotice({ kind: "success", text: plan.success });
    tellOtherTabs(plan.orgId);
    return result;
  } catch (e: any) {
    bumpPending(all, -1);
    if (histId && plan.history) dropHistory(plan.history.itemId, histId);
    // Put back only records nobody has changed since this change was shown.
    const items = { ...state.items };
    for (const id of itemIds) {
      if (id.startsWith("tmp:") || !beforeItems[id]) delete items[id];
      else if (state.items[id]?.lock_version === optLock[id]) items[id] = beforeItems[id]!;
    }
    const tasks = { ...state.tasks };
    for (const id of taskIds) {
      if (id.startsWith("tmp:") || !beforeTasks[id]) delete tasks[id];
      else if (state.tasks[id]?.lock_version === optLock[id]) tasks[id] = beforeTasks[id]!;
    }
    const registers = { ...state.registers };
    for (const id of regIds) {
      if (id.startsWith("tmp:") || !beforeRegs[id]) delete registers[id];
      else registers[id] = beforeRegs[id]!;
    }
    commit({ items, tasks, registers });
    if (tasksLoaded(plan.orgId)) commit({ items: recount(state.items, state.tasks, Array.from(new Set(taskIds.map((t) => state.tasks[t]?.compliance_item_id ?? beforeTasks[t]?.compliance_item_id).filter(Boolean) as string[]))) });
    if (e?.status === 409 && e.current && plan.onConflict) {
      plan.onConflict(e.current);
      setNotice({ kind: "error", text: `${e.message || "Someone else changed this."}` });
    } else {
      setNotice({ kind: "error", text: `${plan.failure}: ${String(e?.message || "unknown error").replace(/\.$/, "")}. Nothing was changed.` });
      void refreshWorkspace(plan.orgId, false);
    }
    return null;
  }
}

/** Only send a lock version when no other save of the same record is in flight (its optimistic version is not on the server yet). */
function lockFor(id: string, lock: number): { lock_version?: number } {
  return (state.pending[id] ?? 0) > 0 ? {} : { lock_version: lock };
}

function fillItem(item: ItemRead) {
  putServer({ item });
}

function lookupUser(orgId: string, userId: string | null) {
  if (!userId) return null;
  const m = (state.members[orgId] || []).find((x) => x.user.id === userId);
  return m ? { id: m.user.id, full_name: m.user.full_name, email: m.user.email } : null;
}

// ------------------------------------------------------------------------------------ item changes
export type ItemChange = {
  department_id?: string | null;
  assigned_lead_id?: string | null;
  internal_deadline?: string | null;
  internal_code?: string | null;
  notes?: string | null;
};

/** Department, lead, internal deadline, code or notes. Shown at once; saved in the background. */
export function changeItem(orgId: string, itemId: string, change: ItemChange): Promise<unknown> {
  const cur = state.items[itemId];
  if (!cur) return Promise.resolve(null);
  const local: Partial<ItemRead> = {};
  if ("department_id" in change) local.department_id = change.department_id ?? null;
  if ("assigned_lead_id" in change) local.assigned_lead = lookupUser(orgId, change.assigned_lead_id ?? null);
  if ("internal_deadline" in change) local.internal_deadline = change.internal_deadline ?? null;
  if ("internal_code" in change) local.internal_code = change.internal_code || null;
  if ("notes" in change) local.notes = change.notes || null;
  const lk = lockFor(itemId, cur.lock_version);
  return mutate({
    orgId,
    items: [itemId],
    optimistic: () => setItemLocal(itemId, local),
    request: () => api.patchItem(orgId, itemId, { ...change, ...lk }),
    done: (item) => fillItem(item),
    failure: "Could not save",
    onConflict: (current) => fillItem(current),
    history: { itemId, action: "ITEM_UPDATED", entity_type: "compliance_item", entity_id: itemId, before: historyBefore(cur, change), after: historyAfter(change) },
  });
}

function historyBefore(it: ItemRead, change: ItemChange) {
  const b: Record<string, unknown> = {};
  if ("department_id" in change) b.department_id = it.department_id;
  if ("assigned_lead_id" in change) b.assigned_lead_id = it.assigned_lead?.id ?? null;
  if ("internal_deadline" in change) b.internal_deadline = it.internal_deadline;
  if ("internal_code" in change) b.internal_code = it.internal_code;
  if ("notes" in change) b.notes = it.notes;
  return b;
}
function historyAfter(change: ItemChange) {
  return { ...change };
}

export type MoveTo = "IN_PROGRESS" | "EVIDENCE_SUBMITTED" | "EXEMPTED" | "NOT_STARTED" | "REOPEN";

/** Start, send for sign-off, exempt, remove exemption, reopen. */
export function moveItem(orgId: string, itemId: string, to: MoveTo, reason?: string): Promise<unknown> {
  const cur = state.items[itemId];
  if (!cur) return Promise.resolve(null);
  const actor = currentActor();
  const target = to === "REOPEN" ? "IN_PROGRESS" : to;
  const local: Partial<ItemRead> = { status: target as ItemRead["status"] };
  if (target !== "EVIDENCE_SUBMITTED") {
    local.submitted_for_signoff_by = null;
    local.submitted_for_signoff_at = null;
  } else {
    local.submitted_for_signoff_by = actor;
    local.submitted_for_signoff_at = new Date().toISOString();
  }
  local.signed_off_by = null;
  local.signed_off_at = null;
  local.exemption_reason = target === "EXEMPTED" ? reason ?? null : null;
  const lk = lockFor(itemId, cur.lock_version);
  const label = { IN_PROGRESS: "Item started.", EVIDENCE_SUBMITTED: "Sent for sign-off.", EXEMPTED: "Item exempted.", NOT_STARTED: "Exemption removed.", REOPEN: "Item reopened." }[to];
  return mutate({
    orgId,
    items: [itemId],
    optimistic: () => setItemLocal(itemId, local),
    request: () => (to === "REOPEN" ? api.reopenItem(orgId, itemId, reason || "") : api.changeItemStatus(orgId, itemId, { to, reason, ...lk })),
    done: (item) => fillItem(item as ItemRead),
    success: label,
    failure: "Could not save",
    onConflict: (current) => fillItem(current),
    history: { itemId, action: "ITEM_STATUS_CHANGED", entity_type: "compliance_item", entity_id: itemId, before: { status: cur.status }, after: { status: target, ...(reason ? { reason } : {}) } },
  });
}

/** Approves or sends back an item that is waiting for sign-off. */
export function signOffItem(orgId: string, itemId: string, decision: "APPROVED" | "REJECTED", comments: string): Promise<unknown> {
  const cur = state.items[itemId];
  if (!cur) return Promise.resolve(null);
  const actor = currentActor();
  const approved = decision === "APPROVED";
  const local: Partial<ItemRead> = approved
    ? { status: "COMPLIANT", signed_off_by: actor, signed_off_at: new Date().toISOString() }
    : { status: "IN_PROGRESS", submitted_for_signoff_by: null, submitted_for_signoff_at: null };
  return mutate({
    orgId,
    items: [itemId],
    optimistic: () => setItemLocal(itemId, local),
    request: () => api.signoffItem(orgId, itemId, { decision, comments }),
    done: (r) => putServer({ item: r.item, itemReview: r.review }),
    success: approved ? "Item signed off as compliant." : "Item sent back.",
    failure: "Could not save",
    history: { itemId, action: "ITEM_SIGNED_OFF", entity_type: "compliance_item", entity_id: itemId, before: { status: cur.status }, after: { status: local.status, reason: comments || undefined } },
  });
}

/** "Mark as reviewed" on a circular change. The banner goes at once. */
export function acknowledgeSourceChange(orgId: string, itemId: string, note: string): Promise<unknown> {
  const cur = state.items[itemId];
  if (!cur) return Promise.resolve(null);
  return mutate({
    orgId,
    items: [itemId],
    optimistic: () => setItemLocal(itemId, { source_change: null }),
    request: () => api.acknowledgeChange(orgId, itemId, note),
    done: (item) => fillItem(item),
    success: "Marked as reviewed.",
    failure: "Could not save",
    history: { itemId, action: "ITEM_SOURCE_CHANGE_ACKNOWLEDGED", entity_type: "compliance_item", entity_id: itemId, after: { note } },
  });
}

// ------------------------------------------------------------------------------------ tasks
export interface NewTask {
  title: string;
  description?: string | null;
  assigned_to_user_id?: string | null;
  due_date: string;
  priority: string;
}

export function addTask(orgId: string, itemId: string, t: NewTask): Promise<unknown> {
  const item = state.items[itemId];
  if (!item) return Promise.resolve(null);
  const tempId = `tmp:${Math.random().toString(36).slice(2)}`;
  const now = new Date().toISOString();
  const placeholder: TaskRead = normTask({
    id: tempId,
    organization_id: orgId,
    compliance_item_id: itemId,
    title: t.title,
    description: t.description ?? null,
    assigned_to_user_id: t.assigned_to_user_id ?? null,
    assigned_to: lookupUser(orgId, t.assigned_to_user_id ?? null),
    due_date: t.due_date,
    priority: t.priority,
    status: "PENDING",
    is_overdue: false,
    days_left: null,
    cancelled_reason: null,
    evidence_count: 0,
    uploader_ids: [],
    lock_version: 1,
    created_at: now,
    updated_at: now,
  });
  const before = item;
  return mutate({
    orgId,
    items: [itemId],
    tasks: [tempId],
    optimistic: () => {
      const tasks = { ...state.tasks, [tempId]: placeholder };
      const status = item.status === "NOT_STARTED" || item.status === "EVIDENCE_SUBMITTED" ? "IN_PROGRESS" : item.status;
      const items = { ...state.items, [itemId]: normItem({ ...item, status, submitted_for_signoff_by: status === "IN_PROGRESS" ? null : item.submitted_for_signoff_by, submitted_for_signoff_at: status === "IN_PROGRESS" ? null : item.submitted_for_signoff_at, lock_version: item.lock_version + 1 }) };
      commit({ tasks, items: recount(items, tasks, [itemId]) });
    },
    request: () => api.createTask(orgId, { compliance_item_id: itemId, ...t }),
    done: (r) => {
      const tasks = { ...state.tasks };
      delete tasks[tempId];
      commit({ tasks });
      putServer({ task: r.task, item: r.item });
    },
    success: "Task added.",
    failure: "Could not add the task",
    history: { itemId, action: "TASK_CREATED", entity_type: "compliance_task", entity_id: tempId, after: { title: t.title }, before: { status: before.status } },
  });
}

export type TaskChange = { title?: string; description?: string | null; assigned_to_user_id?: string | null; due_date?: string; priority?: string; status?: "PENDING" | "IN_PROGRESS" };

export function changeTask(orgId: string, taskId: string, change: TaskChange): Promise<unknown> {
  const cur = state.tasks[taskId];
  const item = cur ? state.items[cur.compliance_item_id] : undefined;
  if (!cur || !item) return Promise.resolve(null);
  const local: Partial<TaskRead> = { ...change } as Partial<TaskRead>;
  if ("assigned_to_user_id" in change) local.assigned_to = lookupUser(orgId, change.assigned_to_user_id ?? null);
  const startsWork = change.status === "IN_PROGRESS" && item.status === "NOT_STARTED";
  const lk = lockFor(taskId, cur.lock_version);
  return mutate({
    orgId,
    items: [item.id],
    tasks: [taskId],
    optimistic: () => {
      setTaskLocal(taskId, local);
      if (startsWork) setItemLocal(item.id, { status: "IN_PROGRESS" });
    },
    request: () => api.patchTask(orgId, taskId, { ...change, ...lk }),
    done: (r) => putServer({ task: r.task, item: r.item }),
    failure: "Could not save",
    onConflict: (current) => putServer({ task: current }),
    history: change.status && Object.keys(change).length === 1
      ? { itemId: item.id, action: "TASK_STATUS_CHANGED", entity_type: "compliance_task", entity_id: taskId, before: { status: cur.status }, after: { status: change.status } }
      : { itemId: item.id, action: "TASK_UPDATED", entity_type: "compliance_task", entity_id: taskId, after: { title: change.title ?? cur.title } },
  });
}

export function cancelTaskNow(orgId: string, taskId: string, reason: string): Promise<unknown> {
  const cur = state.tasks[taskId];
  const item = cur ? state.items[cur.compliance_item_id] : undefined;
  if (!cur || !item) return Promise.resolve(null);
  return mutate({
    orgId,
    items: [item.id],
    tasks: [taskId],
    optimistic: () => setTaskLocal(taskId, { status: "CANCELLED", cancelled_reason: reason }),
    request: () => api.cancelTask(orgId, taskId, reason),
    done: (r) => putServer({ task: r.task, item: r.item }),
    success: "Task cancelled.",
    failure: "Could not cancel the task",
    history: { itemId: item.id, action: "TASK_STATUS_CHANGED", entity_type: "compliance_task", entity_id: taskId, before: { status: cur.status }, after: { status: "CANCELLED", reason } },
  });
}

/** Approve, ask for changes or reject the evidence on a task. */
export function decideTask(orgId: string, taskId: string, decision: "APPROVED" | "CHANGES_REQUESTED" | "REJECTED", comments: string): Promise<unknown> {
  const cur = state.tasks[taskId];
  const item = cur ? state.items[cur.compliance_item_id] : undefined;
  if (!cur || !item) return Promise.resolve(null);
  const status = ({ APPROVED: "APPROVED", CHANGES_REQUESTED: "IN_PROGRESS", REJECTED: "REJECTED" } as const)[decision];
  return mutate({
    orgId,
    items: [item.id],
    tasks: [taskId],
    optimistic: () => {
      setTaskLocal(taskId, { status });
      if (status !== "APPROVED" && item.status === "EVIDENCE_SUBMITTED") setItemLocal(item.id, { status: "IN_PROGRESS", submitted_for_signoff_by: null, submitted_for_signoff_at: null });
    },
    request: () => api.reviewTask(orgId, taskId, { decision, comments }),
    done: (r) => putServer({ task: r.task, item: r.item, taskReview: r.review }),
    success: decision === "APPROVED" ? "Evidence approved." : decision === "REJECTED" ? "Evidence rejected." : "Changes requested.",
    failure: "Could not save",
    history: { itemId: item.id, action: "TASK_REVIEWED", entity_type: "compliance_task", entity_id: taskId, before: { status: cur.status }, after: { status, decision, comments } },
  });
}

// ------------------------------------------------------------------------------------ evidence
const uploadFiles = new Map<string, { file: File; notes: string }>();
const uploadAborts = new Map<string, () => void>();

function patchUpload(id: string, change: Partial<UploadRow>) {
  const cur = state.uploads[id];
  if (!cur) return;
  commit({ uploads: { ...state.uploads, [id]: { ...cur, ...change } } });
}

export function dismissUpload(id: string) {
  const uploads = { ...state.uploads };
  delete uploads[id];
  uploadFiles.delete(id);
  commit({ uploads });
}

/** Uploads a file. The task shows "Evidence submitted" at once; a failed upload shows a red row with Try again. */
export function startUpload(orgId: string, taskId: string, file: File, notes: string, existingId?: string): Promise<unknown> {
  const task = state.tasks[taskId];
  const item = task ? state.items[task.compliance_item_id] : undefined;
  if (!task || !item) return Promise.resolve(null);
  const id = existingId ?? `up:${Math.random().toString(36).slice(2)}`;
  const problem = checkEvidenceFile(file);
  const base: UploadRow = { id, orgId, taskId, itemId: item.id, fileName: file.name, size: file.size, progress: 0, state: "uploading" };
  if (problem) {
    commit({ uploads: { ...state.uploads, [id]: { ...base, state: "error", error: problem } } });
    uploadFiles.set(id, { file, notes });
    return Promise.resolve(null);
  }
  uploadFiles.set(id, { file, notes });
  commit({ uploads: { ...state.uploads, [id]: base } });
  const me = currentActor();
  const goesSubmitted = ["PENDING", "IN_PROGRESS", "REJECTED"].includes(task.status);
  return mutate({
    orgId,
    items: [item.id],
    tasks: [taskId],
    optimistic: () => {
      setTaskLocal(taskId, {
        status: goesSubmitted ? "SUBMITTED" : task.status,
        evidence_count: task.evidence_count + 1,
        uploader_ids: me && !task.uploader_ids.includes(me.id) ? [...task.uploader_ids, me.id] : task.uploader_ids,
      });
      if (item.status === "NOT_STARTED") setItemLocal(item.id, { status: "IN_PROGRESS" });
    },
    request: () => {
      const { promise, abort } = api.uploadEvidence(orgId, taskId, file, notes, (p) => patchUpload(id, { progress: p }));
      uploadAborts.set(id, abort);
      return promise;
    },
    done: (r) => {
      uploadAborts.delete(id);
      putServer({ task: r.task, item: r.item, evidence: r.evidence });
      dismissUpload(id);
    },
    success: "File uploaded.",
    failure: "Could not upload the file",
    history: { itemId: item.id, action: "EVIDENCE_UPLOADED", entity_type: "task_evidence", entity_id: taskId, after: { filename: file.name, sha256: "" } },
  }).then((r) => {
    if (r === null) {
      uploadAborts.delete(id);
      const message = state.notice?.kind === "error" ? state.notice.text : "Upload failed.";
      patchUpload(id, { state: "error", error: message.replace(/^Could not upload the file: /, "").replace(/ Nothing was changed\.$/, "") });
      setNotice(null);
    }
    return r;
  });
}

export function retryUpload(id: string): Promise<unknown> {
  const row = state.uploads[id];
  const keep = uploadFiles.get(id);
  if (!row || !keep) return Promise.resolve(null);
  return startUpload(row.orgId, row.taskId, keep.file, keep.notes, id);
}

export function withdrawFile(orgId: string, taskId: string, evidenceId: string, reason: string): Promise<unknown> {
  const task = state.tasks[taskId];
  const item = task ? state.items[task.compliance_item_id] : undefined;
  const ev = state.evidence[evidenceId];
  if (!task || !item || !ev) return Promise.resolve(null);
  const before = ev;
  const left = Math.max(0, task.evidence_count - 1);
  return mutate({
    orgId,
    items: [item.id],
    tasks: [taskId],
    optimistic: () => {
      commit({ evidence: { ...state.evidence, [evidenceId]: { ...ev, withdrawn_at: new Date().toISOString(), withdrawn_by: currentActor() } } });
      setTaskLocal(taskId, { evidence_count: left, status: left === 0 && task.status === "SUBMITTED" ? "IN_PROGRESS" : task.status });
    },
    request: () => api.withdrawEvidence(orgId, taskId, evidenceId, reason),
    done: (r) => putServer({ task: r.task, item: r.item, evidence: r.evidence }),
    success: "File withdrawn.",
    failure: "Could not withdraw the file",
    history: { itemId: item.id, action: "EVIDENCE_WITHDRAWN", entity_type: "task_evidence", entity_id: evidenceId, after: { reason } },
  }).then((r) => {
    if (r === null) commit({ evidence: { ...state.evidence, [evidenceId]: before } });
    return r;
  });
}

// ------------------------------------------------------------------------------------ registers
export async function addRegister(orgId: string, title: string, description: string): Promise<string | null> {
  const tempId = `tmp:${Math.random().toString(36).slice(2)}`;
  const now = new Date().toISOString();
  const placeholder: RegisterRead = { id: tempId, organization_id: orgId, title, description: description || null, is_active: true, created_at: now, updated_at: now, item_counts: emptyCounts(), source_document_ids: [] };
  const res = await mutate({
    orgId,
    registers: [tempId],
    optimistic: () => commit({ registers: { ...state.registers, [tempId]: placeholder } }),
    request: () => api.createRegister(orgId, { title, description: description || null }),
    done: (r) => {
      const registers = { ...state.registers };
      delete registers[tempId];
      registers[r.id] = r;
      commit({ registers });
    },
    success: "Register created.",
    failure: "Could not create the register",
  });
  return res ? res.id : null;
}

function emptyCounts() {
  return { total: 0, not_started: 0, in_progress: 0, evidence_submitted: 0, compliant: 0, exempted: 0, overdue: 0, flagged: 0 };
}

export function changeRegister(orgId: string, registerId: string, change: { title?: string; description?: string | null; is_active?: boolean }): Promise<unknown> {
  const cur = state.registers[registerId];
  if (!cur) return Promise.resolve(null);
  return mutate({
    orgId,
    registers: [registerId],
    optimistic: () => commit({ registers: { ...state.registers, [registerId]: { ...cur, ...change } as RegisterRead } }),
    request: () => api.updateRegister(orgId, registerId, change),
    done: (r) => commit({ registers: { ...state.registers, [r.id]: r } }),
    success: change.is_active === false ? "Register archived." : change.is_active === true ? "Register restored." : undefined,
    failure: "Could not save the register",
  });
}

export interface AddSource {
  documentId: string;
  reference: string | null;
  title: string;
  publicationDate: string | null;
  versionId: string | null;
  fileSha256?: string | null;
}

function placeholderItem(orgId: string, registerId: string, doc: AddSource, o: AddableObligation, index: number): ItemRead {
  const now = new Date().toISOString();
  return normItem({
    id: `tmp:${Math.random().toString(36).slice(2)}`,
    organization_id: orgId,
    register_id: registerId,
    internal_code: null,
    obligation_id: o.id,
    obligation_title: o.title,
    requirement_description: null,
    obligation_type: o.obligation_type,
    applicability_summary: null,
    frequency: null,
    regulatory_deadline: o.regulatory_deadline,
    deadline_description: null,
    internal_deadline: null,
    effective_deadline: o.regulatory_deadline,
    status: "NOT_STARTED",
    display_status: "NOT_STARTED",
    is_overdue: false,
    days_left: null,
    department_id: null,
    assigned_lead: null,
    notes: null,
    exemption_reason: null,
    submitted_for_signoff_by: null,
    submitted_for_signoff_at: null,
    signed_off_by: null,
    signed_off_at: null,
    source: {
      document_id: doc.documentId,
      version_id: doc.versionId,
      reference_number: doc.reference,
      title: doc.title,
      publication_date: doc.publicationDate,
      page_number: o.page_number,
      quote: o.quote,
      quote_span_ids: null,
      quote_boxes: null,
      file_sha256: doc.fileSha256 ?? null,
      page_link: null,
      in_force_status: "IN_FORCE",
      in_force_by: null,
      current_version_id: doc.versionId,
      is_withdrawn: false,
    },
    source_change: null,
    task_counts: { total: 0, open: 0, submitted: 0, approved: 0, overdue: 0 },
    evidence_count: 0,
    lock_version: 1,
    created_at: new Date(Date.now() + index).toISOString(),
    updated_at: now,
  });
}

/** Adds checked obligations of a circular to a register (or to a new register). They appear at once with a pending look. */
export async function addObligations(
  orgId: string,
  target: { registerId: string } | { newTitle: string },
  doc: AddSource,
  chosen: AddableObligation[]
): Promise<{ registerId: string; skipped: Skipped[] } | null> {
  const isNew = "newTitle" in target;
  const registerId = isNew ? `tmp:${Math.random().toString(36).slice(2)}` : target.registerId;
  const placeholders = chosen.map((o, i) => placeholderItem(orgId, registerId, doc, o, i));
  const ids = placeholders.map((p) => p.id);
  const now = new Date().toISOString();
  const ids_ = chosen.map((o) => o.id);
  const res = await mutate({
    orgId,
    items: ids,
    registers: isNew ? [registerId] : [],
    optimistic: () => {
      const items = { ...state.items };
      placeholders.forEach((p) => (items[p.id] = p));
      const registers = isNew
        ? { ...state.registers, [registerId]: { id: registerId, organization_id: orgId, title: target.newTitle, description: null, is_active: true, created_at: now, updated_at: now, item_counts: emptyCounts(), source_document_ids: [doc.documentId] } as RegisterRead }
        : state.registers;
      commit({ items, registers });
    },
    request: async () => {
      if (isNew) return api.createRegisterFromDocument(orgId, { document_id: doc.documentId, title: target.newTitle, obligation_ids: ids_ });
      const r = await api.addItemsFromDocument(orgId, registerId, { document_id: doc.documentId, obligation_ids: ids_ });
      return { items: r.items, skipped: r.skipped, register: undefined as RegisterRead | undefined };
    },
    done: (r) => {
      const items = { ...state.items };
      ids.forEach((id) => delete items[id]);
      r.items.forEach((it) => (items[it.id] = normItem(it)));
      const registers = { ...state.registers };
      if (isNew) delete registers[registerId];
      if (r.register) registers[r.register.id] = r.register;
      commit({ items: tasksLoaded(orgId) ? recount(items, state.tasks) : items, registers });
      void loadRegisters(orgId, true);
    },
    failure: "Could not add the items",
  });
  if (!res) return null;
  return { registerId: res.register ? res.register.id : registerId, skipped: res.skipped };
}

// ------------------------------------------------------------------------------------ settings: members and departments
export function addMemberNow(orgId: string, email: string, role: string, departmentId: string | null): Promise<MemberRead | null> {
  return (async () => {
    try {
      const m = await api.addMemberByEmail(orgId, { email, role, department_id: departmentId });
      commit({ members: { ...state.members, [orgId]: [...(state.members[orgId] || []), m] } });
      void loadDepartments(orgId, true);
      setNotice({ kind: "success", text: `${m.user.full_name} added.` });
      tellOtherTabs(orgId);
      return m;
    } catch (e: any) {
      setNotice({ kind: "error", text: e?.message || "Could not add that person." });
      return null;
    }
  })();
}

export function changeMember(orgId: string, memberId: string, change: { role?: string; department_id?: string | null; status?: string }): Promise<unknown> {
  const list = state.members[orgId] || [];
  const cur = list.find((m) => m.id === memberId);
  if (!cur) return Promise.resolve(null);
  const before = list;
  const apply = (m: MemberRead) => ({ ...m, ...change });
  commit({ members: { ...state.members, [orgId]: list.map((m) => (m.id === memberId ? apply(m) : m)) } });
  bumpPending([memberId], 1);
  return api
    .updateMember(orgId, memberId, change)
    .then((m) => {
      bumpPending([memberId], -1);
      commit({ members: { ...state.members, [orgId]: (state.members[orgId] || []).map((x) => (x.id === memberId ? m : x)) } });
      void loadDepartments(orgId, true);
      if (state.me[orgId]?.membership.id === memberId) void loadMe(orgId, true);
      tellOtherTabs(orgId);
    })
    .catch((e) => {
      bumpPending([memberId], -1);
      commit({ members: { ...state.members, [orgId]: before } });
      setNotice({ kind: "error", text: `Could not save: ${String(e?.message || "unknown error").replace(/\.$/, "")}. Nothing was changed.` });
    });
}

export function addDepartmentNow(orgId: string, name: string, headUserId: string | null): Promise<boolean> {
  return (async () => {
    const tempId = `tmp:${Math.random().toString(36).slice(2)}`;
    const before = state.departments[orgId] || [];
    const placeholder: DepartmentRead = { id: tempId, organization_id: orgId, name, head_user_id: headUserId, head: null, member_count: 0, open_item_count: 0, created_at: new Date().toISOString() };
    commit({ departments: { ...state.departments, [orgId]: [...before, placeholder].sort((a, b) => a.name.localeCompare(b.name)) } });
    try {
      const d = await api.createDepartment(orgId, { name, head_user_id: headUserId });
      commit({ departments: { ...state.departments, [orgId]: [...(state.departments[orgId] || []).filter((x) => x.id !== tempId), d].sort((a, b) => a.name.localeCompare(b.name)) } });
      tellOtherTabs(orgId);
      return true;
    } catch (e: any) {
      commit({ departments: { ...state.departments, [orgId]: before } });
      setNotice({ kind: "error", text: `Could not add the department: ${e?.message || "unknown error"}. Nothing was changed.` });
      return false;
    }
  })();
}

export function changeDepartment(orgId: string, deptId: string, change: { name?: string; head_user_id?: string | null }): Promise<unknown> {
  const before = state.departments[orgId] || [];
  const cur = before.find((d) => d.id === deptId);
  if (!cur) return Promise.resolve(null);
  const head = "head_user_id" in change ? lookupUser(orgId, change.head_user_id ?? null) : cur.head;
  commit({ departments: { ...state.departments, [orgId]: before.map((d) => (d.id === deptId ? { ...d, ...change, head } : d)) } });
  return api
    .updateDepartment(orgId, deptId, change)
    .then((d) => {
      commit({ departments: { ...state.departments, [orgId]: (state.departments[orgId] || []).map((x) => (x.id === deptId ? d : x)) } });
      tellOtherTabs(orgId);
    })
    .catch((e) => {
      commit({ departments: { ...state.departments, [orgId]: before } });
      setNotice({ kind: "error", text: `Could not save: ${String(e?.message || "unknown error").replace(/\.$/, "")}. Nothing was changed.` });
    });
}

export function removeDepartment(orgId: string, deptId: string): Promise<unknown> {
  const before = state.departments[orgId] || [];
  commit({ departments: { ...state.departments, [orgId]: before.filter((d) => d.id !== deptId) } });
  return api
    .deleteDepartment(orgId, deptId)
    .then(() => {
      void loadMembers(orgId, true);
      tellOtherTabs(orgId);
    })
    .catch((e) => {
      commit({ departments: { ...state.departments, [orgId]: before } });
      setNotice({ kind: "error", text: `Could not delete: ${e?.message || "unknown error"}. Nothing was changed.` });
    });
}
