"use client";

/**
 * One shared copy of the person's alerts. The bell, the panel, the inbox, the settings screen and the
 * tab title all read from here, so a change on one of them shows on all of them in the same moment.
 *
 * - One record per alert, by id. Lists are selectors over that map.
 * - A tap is shown first and saved in the background. Only the alert it touched is put back if the save
 *   fails.
 * - A poll or a load never overwrites an alert that is being saved, and never replaces the unread count
 *   while a save is in flight (the epoch counter marks which answers are older than a local change).
 * - Other tabs hear about every change through a BroadcastChannel and apply it without a request.
 * - Polling: every 15 seconds while the tab is visible, at once when the tab is shown or focused.
 */
import { useSyncExternalStore } from "react";
import { AUTH_CHANGED_EVENT, getStoredUser } from "./api";
import * as api from "./alertsApi";
import type { AlertRead, EmailStatus, OutboxRow, PreferencesRead } from "./alertsApi";
import { getWorkspaceState, refreshWorkspace } from "./workspaceStore";

export const ALERTS_POLL_MS = Number(process.env.NEXT_PUBLIC_ALERTS_POLL_MS) > 0 ? Number(process.env.NEXT_PUBLIC_ALERTS_POLL_MS) : 15000;

// ------------------------------------------------------------------------------------ state
export interface AlertsNotice {
  kind: "error" | "success" | "info";
  text: string;
}

export interface ViewState {
  status: "idle" | "loading" | "ok" | { error: string };
  nextBefore: string | null;
  loadingMore: boolean;
}

export interface AlertsState {
  userId: string | null;
  alerts: Record<string, AlertRead>;
  /** One entry per list the inbox has asked the server for, keyed "filter|group". "all|" is the base list. */
  views: Record<string, ViewState>;
  newestSeen: string | null;
  unread: number;
  pending: Record<string, number>;
  prefs: PreferencesRead | null;
  prefsLoaded: "idle" | "loading" | "ok" | { error: string };
  /** Settings taps not yet confirmed by the server. */
  prefsPending: number;
  /** Changes each time the server confirms a save, so the screen can flash "Saved". */
  prefsSavedAt: number;
  emailConfigured: boolean;
  emailStatus: EmailStatus | null;
  outbox: OutboxRow[] | null;
  notice: AlertsNotice | null;
}

function emptyState(userId: string | null = null): AlertsState {
  return {
    userId,
    alerts: {},
    views: {},
    newestSeen: null,
    unread: 0,
    pending: {},
    prefs: null,
    prefsLoaded: "idle",
    prefsPending: 0,
    prefsSavedAt: 0,
    emailConfigured: false,
    emailStatus: null,
    outbox: null,
    notice: null,
  };
}

let state: AlertsState = emptyState();
const listeners = new Set<() => void>();
let noticeTimer: ReturnType<typeof setTimeout> | null = null;
/** Bumped when the person changes, so answers that belong to the old person are thrown away. */
let session = 0;
/** Bumped at the start and end of every local change. */
let epoch = 0;
/** The epoch of the last local change to each alert. */
let touched: Record<string, number> = {};

function commit(next: Partial<AlertsState>) {
  state = { ...state, ...next };
  listeners.forEach((l) => l());
}

function subscribe(l: () => void) {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
}

export function getAlertsState() {
  return state;
}

export function useAlerts(): AlertsState {
  return useSyncExternalStore(subscribe, getAlertsState, getAlertsState);
}

export function setAlertsNotice(notice: AlertsNotice | null) {
  if (noticeTimer) clearTimeout(noticeTimer);
  commit({ notice });
  if (notice && notice.kind !== "error") noticeTimer = setTimeout(() => commit({ notice: null }), 4500);
}
export const clearAlertsNotice = () => setAlertsNotice(null);

// ------------------------------------------------------------------------------------ selectors
export const GROUP_ALIASES: Record<string, string[]> = { deadlines: ["due_soon", "overdue"] };

export function groupsFor(group: string | null | undefined): string[] | null {
  if (!group) return null;
  return GROUP_ALIASES[group] ?? [group];
}

export const viewKey = (filter: "all" | "unread", group: string | null) => `${filter}|${group ?? ""}`;

function time(a: AlertRead) {
  const t = Date.parse(a.created_at);
  return Number.isNaN(t) ? 0 : t;
}

function newestFirst(a: AlertRead, b: AlertRead) {
  return time(b) - time(a) || (a.id < b.id ? 1 : -1);
}

export function selectAlerts(s: AlertsState, opts: { filter?: "all" | "unread"; group?: string | null } = {}): AlertRead[] {
  const groups = groupsFor(opts.group);
  return Object.values(s.alerts)
    .filter((a) => (opts.filter === "unread" ? !a.read_at : true) && (!groups || groups.includes(a.group)))
    .sort(newestFirst);
}

export const selectPanelAlerts = (s: AlertsState) => selectAlerts(s).slice(0, 8);
export const unreadCount = (s: AlertsState) => s.unread;

export function selectView(s: AlertsState, filter: "all" | "unread", group: string | null): ViewState {
  return s.views[viewKey(filter, group)] ?? { status: "idle", nextBefore: null, loadingMore: false };
}

// ------------------------------------------------------------------------------------ plumbing
const inflight = new Map<string, Promise<void>>();
function once(key: string, run: () => Promise<void>): Promise<void> {
  const existing = inflight.get(key);
  if (existing) return existing;
  const p = run().finally(() => inflight.delete(key));
  inflight.set(key, p);
  return p;
}

function totalPending(): number {
  let n = 0;
  for (const v of Object.values(state.pending)) n += v;
  return n;
}

function beginWrite(ids: string[]) {
  epoch++;
  const pending = { ...state.pending };
  for (const id of ids) {
    pending[id] = (pending[id] ?? 0) + 1;
    touched[id] = epoch;
  }
  commit({ pending });
}

function endWrite(ids: string[]) {
  epoch++;
  const pending = { ...state.pending };
  for (const id of ids) {
    pending[id] = Math.max(0, (pending[id] ?? 0) - 1);
    if (pending[id] === 0) delete pending[id];
    touched[id] = epoch;
  }
  commit({ pending });
}

/** Adds server copies to the map, skipping any alert that is being saved or changed since the request began. */
function mergeAlerts(list: AlertRead[], startEpoch: number): string[] {
  const alerts = { ...state.alerts };
  const added: string[] = [];
  for (const a of list) {
    if ((state.pending[a.id] ?? 0) > 0) continue;
    if ((touched[a.id] ?? 0) > startEpoch) continue;
    if (!alerts[a.id]) added.push(a.id);
    alerts[a.id] = a;
  }
  commit({ alerts });
  return added;
}

function later(a: string | null, b: string | null): string | null {
  if (!a) return b;
  if (!b) return a;
  return Date.parse(b) > Date.parse(a) ? b : a;
}

// ------------------------------------------------------------------------------------ other tabs
type TabMessage =
  | { type: "read"; ids: string[]; at: string; unread: number }
  | { type: "unread"; ids: string[]; unread: number }
  | { type: "read-all"; upTo: string; group: string | null; at: string; unread: number }
  | { type: "prefs"; prefs: PreferencesRead }
  | { type: "poll" };

let channel: BroadcastChannel | null = null;
function getChannel(): BroadcastChannel | null {
  if (channel || typeof window === "undefined" || typeof BroadcastChannel === "undefined") return channel;
  try {
    channel = new BroadcastChannel("regwatch-alerts");
    channel.onmessage = (e) => onTabMessage(e.data as TabMessage & { userId?: string | null });
  } catch {
    channel = null;
  }
  return channel;
}

function tell(msg: TabMessage) {
  try {
    getChannel()?.postMessage({ ...msg, userId: state.userId });
  } catch {
    /* other tabs catch up on their next poll or focus */
  }
}

function onTabMessage(msg: TabMessage & { userId?: string | null }) {
  if (!msg || msg.userId !== state.userId) return;
  switch (msg.type) {
    case "read": {
      const alerts = { ...state.alerts };
      for (const id of msg.ids) if (alerts[id] && !alerts[id].read_at) alerts[id] = { ...alerts[id], read_at: msg.at };
      commit({ alerts, unread: msg.unread });
      break;
    }
    case "unread": {
      const alerts = { ...state.alerts };
      for (const id of msg.ids) if (alerts[id]?.read_at) alerts[id] = { ...alerts[id], read_at: null };
      commit({ alerts, unread: msg.unread });
      break;
    }
    case "read-all": {
      const groups = groupsFor(msg.group);
      const upTo = Date.parse(msg.upTo);
      const alerts = { ...state.alerts };
      for (const a of Object.values(alerts)) {
        if (!a.read_at && time(a) <= upTo && (!groups || groups.includes(a.group))) alerts[a.id] = { ...a, read_at: msg.at };
      }
      commit({ alerts, unread: msg.unread });
      break;
    }
    case "prefs":
      commit({ prefs: msg.prefs });
      break;
    case "poll":
      void pollNow(true);
      break;
  }
}

// ------------------------------------------------------------------------------------ session
let prefsTimer: ReturnType<typeof setTimeout> | null = null;
let prefsSaving = false;
let prefsGen = 0;
let lastSaved: PreferencesRead | null = null;

let bound = false;
function bind() {
  if (bound || typeof window === "undefined") return;
  bound = true;
  getChannel();
  window.addEventListener(AUTH_CHANGED_EVENT, () => syncSessionUser());
  startTitle();
}

/** A different person signing in must never see the previous person's alerts. */
export function syncSessionUser() {
  const id = getStoredUser()?.id ?? null;
  if (state.userId !== id) {
    session++;
    epoch = 0;
    touched = {};
    inflight.clear();
    if (prefsTimer) clearTimeout(prefsTimer);
    prefsTimer = null;
    prefsSaving = false;
    prefsGen = 0;
    lastSaved = null;
    state = emptyState(id);
    listeners.forEach((l) => l());
  }
}

function ready(): boolean {
  bind();
  syncSessionUser();
  return !!state.userId;
}

// ------------------------------------------------------------------------------------ loading
function setView(key: string, v: ViewState) {
  commit({ views: { ...state.views, [key]: v } });
}

/** Loads a list. `more` fetches the next older page. The first page of the base list also drops alerts the server no longer shows. */
export function loadView(filter: "all" | "unread" = "all", group: string | null = null, more = false): Promise<void> {
  if (!ready()) return Promise.resolve();
  const key = viewKey(filter, group);
  const current = selectView(state, filter, group);
  if (!more && current.status === "ok") return Promise.resolve();
  if (more && !current.nextBefore) return Promise.resolve();
  return once(`view:${key}:${more}`, async () => {
    const sess = session;
    const startEpoch = epoch;
    const before = more ? current.nextBefore : null;
    setView(key, more ? { ...current, loadingMore: true } : { ...current, status: "loading" });
    try {
      const res = await api.fetchAlerts({ filter, group, before, limit: 30 });
      if (sess !== session) return;
      const settled = epoch === startEpoch && totalPending() === 0;
      const isBase = !more && filter === "all" && !group;
      if (isBase) {
        // Forget alerts that were in this page's time range but are no longer shown (for example a suspended member).
        const ids = new Set(res.alerts.map((a) => a.id));
        const oldest = res.next_before ? Date.parse(res.next_before) : 0;
        const alerts = { ...state.alerts };
        for (const a of Object.values(alerts)) {
          if (!ids.has(a.id) && (state.pending[a.id] ?? 0) === 0 && time(a) >= oldest) delete alerts[a.id];
        }
        commit({ alerts });
      }
      mergeAlerts(res.alerts, startEpoch);
      const patch: Partial<AlertsState> = {};
      if (isBase) patch.newestSeen = later(state.newestSeen, res.alerts[0]?.created_at ?? null);
      if (settled) patch.unread = res.unread_count;
      commit(patch);
      setView(key, { status: "ok", nextBefore: res.next_before, loadingMore: false });
    } catch (e: any) {
      if (sess !== session) return;
      if (more) {
        setView(key, { ...current, loadingMore: false });
        setAlertsNotice({ kind: "error", text: "Could not load older alerts. Try again." });
      } else {
        setView(key, { status: current.status === "ok" ? "ok" : { error: e?.message || "Could not load alerts." }, nextBefore: current.nextBefore, loadingMore: false });
      }
    }
  });
}

export const loadMoreAlerts = (filter: "all" | "unread", group: string | null) => loadView(filter, group, true);

/** Re-reads the first page of the base list from the server. */
function reloadFirstPage(): Promise<void> {
  const key = viewKey("all", null);
  const v = selectView(state, "all", null);
  state = { ...state, views: { ...state.views, [key]: { ...v, status: "idle" } } };
  return loadView("all", null);
}

export const loadAlerts = () => loadView("all", null);

async function fetchDelta(startEpoch: number, sess: number, fromBroadcast: boolean) {
  if (!state.newestSeen) {
    await reloadFirstPage();
    return;
  }
  const res = await api.fetchAlerts({ after: state.newestSeen, limit: 100 });
  if (sess !== session) return;
  if (res.alerts.length >= 100) {
    await reloadFirstPage();
    return;
  }
  // New alerts for the bank that is open: refresh the workspace first, so its screens and the bell change in the same moment.
  const orgId = getWorkspaceState().activeOrgId;
  if (orgId && res.alerts.some((a) => a.organization_id === orgId && !state.alerts[a.id])) {
    try {
      await refreshWorkspace(orgId, false);
    } catch {
      /* the workspace refreshes again on its own timer */
    }
    if (sess !== session) return;
  }
  const added = mergeAlerts(res.alerts, startEpoch);
  const newest = res.alerts.reduce<string | null>((acc, a) => later(acc, a.created_at), null);
  const patch: Partial<AlertsState> = { newestSeen: later(state.newestSeen, newest) };
  if (epoch === startEpoch && totalPending() === 0) patch.unread = res.unread_count;
  commit(patch);
  if (added.length > 0 && !fromBroadcast) tell({ type: "poll" });
}

/** Asks the server for the unread count and fetches anything new. */
export function pollNow(fromBroadcast = false): Promise<void> {
  if (!ready()) return Promise.resolve();
  return once("poll", async () => {
    const sess = session;
    const startEpoch = epoch;
    try {
      const s = await api.fetchSummary();
      if (sess !== session) return;
      const settled = epoch === startEpoch && totalPending() === 0;
      const patch: Partial<AlertsState> = {};
      if (state.emailConfigured !== s.email_configured) patch.emailConfigured = s.email_configured;
      const mismatch = settled && state.unread !== s.unread_count;
      const viewReady = selectView(state, "all", null).status === "ok";
      const newOnes = viewReady && !!s.latest_id && !state.alerts[s.latest_id];
      // When new alerts are coming, the count changes together with them (and with the workspace) below.
      if (settled && !newOnes) patch.unread = s.unread_count;
      commit(patch);
      if (!viewReady) {
        await loadView("all", null);
      } else if (newOnes) {
        await fetchDelta(startEpoch, sess, fromBroadcast);
      } else if (mismatch) {
        // Something changed elsewhere (another device, a suspended seat): read the first page again.
        await reloadFirstPage();
      }
    } catch {
      /* the next poll tries again; the screen keeps what it has */
    }
  });
}

// ------------------------------------------------------------------------------------ read state
async function setReadState(id: string, read: boolean): Promise<void> {
  if (!ready()) return;
  const before = state.alerts[id];
  if (!before) return;
  if (read === !!before.read_at) return;
  const sess = session;
  const stamp = read ? new Date().toISOString() : null;
  const delta = read ? -1 : 1;
  const announce = () =>
    tell(read ? { type: "read", ids: [id], at: stamp as string, unread: state.unread } : { type: "unread", ids: [id], unread: state.unread });
  beginWrite([id]);
  commit({ alerts: { ...state.alerts, [id]: { ...before, read_at: stamp } }, unread: Math.max(0, state.unread + delta) });
  announce();
  try {
    const res = read ? await api.postRead(id) : await api.postUnread(id);
    if (sess !== session) return;
    endWrite([id]);
    commit({ alerts: { ...state.alerts, [id]: res.alert } });
    if (totalPending() === 0 && state.unread !== res.unread_count) {
      commit({ unread: res.unread_count });
      announce();
    }
  } catch (e: any) {
    if (sess !== session) return;
    endWrite([id]);
    // Put back only this alert, and only if nothing newer landed on it.
    if (state.alerts[id]?.read_at === stamp) {
      commit({ alerts: { ...state.alerts, [id]: before }, unread: Math.max(0, state.unread - delta) });
      tell(read ? { type: "unread", ids: [id], unread: state.unread } : { type: "read", ids: [id], at: before.read_at ?? new Date().toISOString(), unread: state.unread });
    }
    setAlertsNotice({ kind: "error", text: read ? "Could not mark as read. Nothing was changed." : "Could not mark as unread. Nothing was changed." });
    if (e?.status === 404) void pollNow();
  }
}

export const markRead = (id: string) => setReadState(id, true);
export const markUnread = (id: string) => setReadState(id, false);

export function toggleRead(id: string) {
  const a = state.alerts[id];
  if (!a) return Promise.resolve();
  return setReadState(id, !a.read_at);
}

export async function markAllRead(group: string | null = null): Promise<void> {
  if (!ready()) return;
  const sess = session;
  const upTo = state.newestSeen ?? new Date().toISOString();
  const upToMs = Date.parse(upTo);
  const groups = groupsFor(group);
  const stamp = new Date().toISOString();
  const changed = Object.values(state.alerts).filter((a) => !a.read_at && time(a) <= upToMs && (!groups || groups.includes(a.group)));
  const ids = changed.map((a) => a.id);
  const key = "*";
  beginWrite([key, ...ids]);
  const alerts = { ...state.alerts };
  for (const a of changed) alerts[a.id] = { ...a, read_at: stamp };
  const stillUnread = Object.values(alerts).filter((a) => !a.read_at).length;
  commit({ alerts, unread: group ? Math.max(0, state.unread - changed.length) : stillUnread });
  tell({ type: "read-all", upTo, group, at: stamp, unread: state.unread });
  try {
    const res = await api.postReadAll(upTo, group);
    if (sess !== session) return;
    endWrite([key, ...ids]);
    if (totalPending() === 0) {
      commit({ unread: res.unread_count });
      tell({ type: "read-all", upTo, group, at: stamp, unread: state.unread });
    }
  } catch {
    if (sess !== session) return;
    endWrite([key, ...ids]);
    const back = { ...state.alerts };
    let restored = 0;
    for (const a of changed) {
      if (back[a.id]?.read_at === stamp) {
        back[a.id] = a;
        restored++;
      }
    }
    commit({ alerts: back, unread: state.unread + restored });
    tell({ type: "unread", ids: changed.map((a) => a.id), unread: state.unread });
    setAlertsNotice({ kind: "error", text: "Could not mark all as read. Nothing was changed." });
  }
}

/** Marks the alert read in the background and goes to what it is about. The page change does not wait for the save. */
export function openAlert(alert: AlertRead, router: { push: (href: string) => void }) {
  void markRead(alert.id);
  router.push(alert.link);
}

// ------------------------------------------------------------------------------------ settings
export function loadPrefs(force = false): Promise<void> {
  if (!ready()) return Promise.resolve();
  if (!force && state.prefsLoaded === "ok") return Promise.resolve();
  return once("prefs", async () => {
    const sess = session;
    const gen = prefsGen;
    if (state.prefsLoaded !== "ok") commit({ prefsLoaded: "loading" });
    try {
      const p = await api.fetchPreferences();
      if (sess !== session) return;
      lastSaved = p;
      // A tap made while this was loading wins.
      if (gen === prefsGen && state.prefsPending === 0) commit({ prefs: p, emailConfigured: p.email_configured, prefsLoaded: "ok" });
      else commit({ prefsLoaded: "ok" });
    } catch (e: any) {
      if (sess !== session) return;
      commit({ prefsLoaded: state.prefs ? "ok" : { error: e?.message || "Could not load your settings." } });
    }
  });
}

/** Shows a settings change at once and saves it after a short pause (several taps become one save). */
export function savePrefs(change: (p: PreferencesRead) => PreferencesRead) {
  if (!ready() || !state.prefs) return;
  prefsGen++;
  commit({ prefs: change(state.prefs), prefsPending: state.prefsPending + 1 });
  tell({ type: "prefs", prefs: state.prefs as PreferencesRead });
  if (prefsTimer) clearTimeout(prefsTimer);
  prefsTimer = setTimeout(() => void flushPrefs(), 400);
}

async function flushPrefs(): Promise<void> {
  if (prefsSaving || !state.prefs) return;
  const sess = session;
  const sentGen = prefsGen;
  const body = state.prefs;
  prefsSaving = true;
  let again = false;
  try {
    const res = await api.putPreferences(body);
    if (sess !== session) return;
    lastSaved = res;
    if (prefsGen === sentGen) {
      commit({ prefs: res, prefsPending: 0, prefsSavedAt: Date.now(), emailConfigured: res.email_configured });
      tell({ type: "prefs", prefs: res });
    } else {
      // More taps came in while saving: keep them, take the new version number, and save again.
      commit({ prefs: { ...(state.prefs as PreferencesRead), lock_version: res.lock_version } });
      again = true;
    }
  } catch (e: any) {
    if (sess !== session) return;
    if (e?.status === 409 && e.current) {
      lastSaved = e.current as PreferencesRead;
      commit({ prefs: e.current as PreferencesRead, prefsPending: 0 });
      tell({ type: "prefs", prefs: e.current as PreferencesRead });
      setAlertsNotice({ kind: "info", text: "Your settings were changed in another window. You now see the latest." });
    } else {
      if (lastSaved) commit({ prefs: lastSaved });
      commit({ prefsPending: 0 });
      if (lastSaved) tell({ type: "prefs", prefs: lastSaved });
      setAlertsNotice({ kind: "error", text: `Could not save your settings: ${String(e?.message || "unknown error").replace(/\.$/, "")}. Nothing was changed.` });
    }
  } finally {
    if (sess === session) {
      prefsSaving = false;
      if (again) void flushPrefs();
    }
  }
}

export function setChannel(group: string, patch: Partial<{ in_app: boolean; email: "OFF" | "INSTANT" | "DIGEST" }>) {
  savePrefs((p) => ({ ...p, channels: { ...p.channels, [group]: { ...p.channels[group], ...patch } } }));
}

export const setEmailEnabled = (on: boolean) => savePrefs((p) => ({ ...p, email_enabled: on }));

function toggled(list: string[], value: string): string[] {
  return list.includes(value) ? list.filter((x) => x !== value) : [...list, value];
}

export const toggleDepartment = (code: string) => savePrefs((p) => ({ ...p, library_department_codes: toggled(p.library_department_codes, code) }));
export const toggleDocumentType = (type: string) => savePrefs((p) => ({ ...p, library_document_types: toggled(p.library_document_types, type) }));

/** Adds a keyword. Returns a plain-English problem, or null when it was added. */
export function addKeyword(raw: string): string | null {
  const word = raw.split(/\s+/).filter(Boolean).join(" ");
  const p = state.prefs;
  if (!p) return "Settings are still loading.";
  if (word.length < 2 || word.length > 60) return "A keyword must be 2 to 60 characters.";
  if (p.library_keywords.some((k) => k.toLowerCase() === word.toLowerCase())) return "That keyword is already in the list.";
  if (p.library_keywords.length >= 20) return "You can add up to 20 keywords.";
  savePrefs((q) => ({ ...q, library_keywords: [...q.library_keywords, word] }));
  return null;
}

export const removeKeyword = (word: string) => savePrefs((p) => ({ ...p, library_keywords: p.library_keywords.filter((k) => k !== word) }));

// ------------------------------------------------------------------------------------ email box (platform staff)
export function loadEmailAdmin(force = false): Promise<void> {
  if (!ready()) return Promise.resolve();
  if (!force && state.emailStatus && state.outbox) return Promise.resolve();
  return once("email-admin", async () => {
    const sess = session;
    try {
      const [status, box] = await Promise.all([api.fetchEmailStatus(), api.fetchOutbox(20)]);
      if (sess !== session) return;
      commit({ emailStatus: status, outbox: box.rows });
    } catch {
      /* the box shows what it has */
    }
  });
}

export async function sendTestEmail(): Promise<{ ok: boolean; text: string }> {
  const email = getStoredUser()?.email ?? "you";
  try {
    const r = await api.postTestEmail();
    void loadEmailAdmin(true);
    return { ok: r.ok, text: r.ok ? `Test email sent to ${email}.` : `Could not send: ${r.detail}` };
  } catch (e: any) {
    void loadEmailAdmin(true);
    return { ok: false, text: `Could not send: ${String(e?.message || "unknown error").replace(/\.$/, "")}` };
  }
}

export async function retryEmail(id: string): Promise<void> {
  const rows = state.outbox ?? [];
  const before = rows.find((r) => r.id === id);
  if (!before) return;
  const sess = session;
  commit({ outbox: rows.map((r) => (r.id === id ? { ...r, status: "PENDING", attempts: 0 } : r)) });
  try {
    const row = await api.postOutboxRetry(id);
    if (sess !== session) return;
    commit({ outbox: (state.outbox ?? []).map((r) => (r.id === id ? row : r)) });
    void loadEmailAdmin(true);
  } catch (e: any) {
    if (sess !== session) return;
    commit({ outbox: (state.outbox ?? []).map((r) => (r.id === id ? before : r)) });
    setAlertsNotice({ kind: "error", text: `Could not retry: ${String(e?.message || "unknown error").replace(/\.$/, "")}. Nothing was changed.` });
  }
}

// ------------------------------------------------------------------------------------ tab title
function applyTitle() {
  if (typeof document === "undefined") return;
  const base = document.title.replace(/^\((\d+|99\+)\)\s/, "");
  const n = state.userId ? state.unread : 0;
  const want = n > 0 ? `(${n > 99 ? "99+" : n}) ${base}` : base;
  if (document.title !== want) document.title = want;
}

function startTitle() {
  listeners.add(applyTitle);
  try {
    new MutationObserver(applyTitle).observe(document.head, { childList: true, subtree: true, characterData: true });
  } catch {
    /* the title just keeps whatever the page set */
  }
}

// ------------------------------------------------------------------------------------ start
/** Starts polling for the signed-in person and loads the first page and the settings in the background. Returns a stop function. */
export function startAlertsSync(): () => void {
  if (!ready()) return () => {};
  const user = getStoredUser();
  void pollNow();
  void loadView("all", null);
  void loadPrefs();
  if (user?.is_superuser) void loadEmailAdmin();
  const timer = setInterval(() => {
    if (!document.hidden) void pollNow();
  }, ALERTS_POLL_MS);
  const onFocus = () => void pollNow();
  const onVisible = () => {
    if (!document.hidden) void pollNow();
  };
  window.addEventListener("focus", onFocus);
  document.addEventListener("visibilitychange", onVisible);
  return () => {
    clearInterval(timer);
    window.removeEventListener("focus", onFocus);
    document.removeEventListener("visibilitychange", onVisible);
  };
}
