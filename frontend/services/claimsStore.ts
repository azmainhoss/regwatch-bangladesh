"use client";

/**
 * One shared copy of the checked view of every circular the screens have opened, and of the review
 * queue, the same pattern as relationshipsStore and workspaceStore. Every screen reads from here, so a
 * change shows on all of them in the same moment.
 *
 * - A decision (approve, fix, reject) or hiding a point shows at once on every screen of this tab: the
 *   review screen moves on, the tab count drops, the circular page and the links view redraw. The save
 *   runs after, and everything is put back (with a message) if it fails.
 * - Other tabs of the same browser hear about it through a BroadcastChannel and read again.
 * - Everyone else is reached by polling: a circular page is read again every few seconds while it is
 *   visible, and the review screen's counts and list every 15 seconds while it is open.
 * - The next five points of the queue, their page lists and their page images are fetched ahead of time.
 */
import { useEffect, useSyncExternalStore } from "react";
import {
  AUTH_CHANGED_EVENT,
  CheckedView,
  ClaimAction,
  ClaimCounts,
  ClaimDecisionBody,
  ClaimDecisionError,
  ClaimItem,
  ClaimSection,
  DocumentPage,
  HiddenPoint,
  RelLink,
  ReviewCounts,
  ReviewQueue,
  ReviewRow,
  askReviewAllClaims,
  askReviewClaim,
  decideClaim,
  fetchClaims,
  fetchDocumentPages,
  fetchReviewCounts,
  fetchReviewPoint,
  fetchReviewQueue,
} from "./api";
import { preloadPageImage } from "./pageImages";
import { loadStatus, refreshAll as refreshLinks, reviewLink, setRelNotice, showLinkDecision } from "./relationshipsStore";
import { REVIEW_TEXT } from "./claimWords";

export interface ClaimsNotice {
  kind: "error" | "success";
  text: string;
}

export interface ReviewNotice {
  kind: "error" | "info";
  text: string;
  /** The point this is about, when it was put back. */
  claimId?: string;
}

export interface QueueState {
  items: ReviewRow[];
  /** Points opened from a link on the circular page; kept in the list until they are decided. */
  pinned: ReviewRow[];
  next: string | null;
  total: number;
  loaded: boolean;
  loading: boolean;
  error: string | null;
}

export interface ClaimsState {
  /** What a reader sees, by circular id. */
  byDoc: Record<string, CheckedView>;
  /** What an administrator sees (every point with its state), by circular id. */
  byDocAdmin: Record<string, CheckedView>;
  /** Points whose decision is being saved. */
  busy: Record<string, boolean>;
  /** Circulars whose "ask for review of all points" is being saved. */
  busyDoc: Record<string, boolean>;
  errors: Record<string, string>;
  notice: ClaimsNotice | null;
  // The review screen
  queue: Record<ReviewQueue, QueueState>;
  counts: ReviewCounts | null;
  countsError: string | null;
  /** Page lists of the circulars in the queue, by "<circular id>:<file id>". */
  pageLists: Record<string, DocumentPage[]>;
  reviewNotice: ReviewNotice | null;
}

const POLL_MS = 5000;
// A circular whose points are settled is re-read once a minute (and at once when the tab comes back into view);
// every 5 s only while its analysis runs or its points are being checked.
const IDLE_POLL_MS = 60000;
const REVIEW_POLL_MS = 15000;
const PRELOAD_AHEAD = 5;
export const SECTIONS: ClaimSection[] = ["summary", "changes", "requirements", "applies_to", "exemptions", "dates", "links", "clauses"];

const emptyQueue = (): QueueState => ({ items: [], pinned: [], next: null, total: 0, loaded: false, loading: false, error: null });

let state: ClaimsState = {
  byDoc: {},
  byDocAdmin: {},
  busy: {},
  busyDoc: {},
  errors: {},
  notice: null,
  queue: { REQUIRED: emptyQueue(), OPTIONAL: emptyQueue() },
  counts: null,
  countsError: null,
  pageLists: {},
  reviewNotice: null,
};
// Counts decisions; an answer fetched before the latest decision is thrown away.
let epoch = 0;
const listeners = new Set<() => void>();

function commit(next: Partial<ClaimsState>) {
  state = { ...state, ...next };
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function getClaimsState() {
  return state;
}

export function useClaimsState(): ClaimsState {
  return useSyncExternalStore(subscribe, getClaimsState, getClaimsState);
}

export function clearClaimsNotice() {
  commit({ notice: null });
}

export function clearReviewNotice() {
  commit({ reviewNotice: null });
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

const viewKey = (docId: string, admin: boolean) => `${admin ? "a" : "u"}:${docId}`;

/** Reads one circular's checked view and puts it in the store. A read that began before a decision is dropped and repeated. */
export function loadDoc(docId: string, admin: boolean): Promise<void> {
  return once(`doc:${viewKey(docId, admin)}`, async () => {
    for (let attempt = 0; attempt < 3; attempt++) {
      const started = epoch;
      try {
        const data = await fetchClaims(docId, admin);
        if (started !== epoch) continue;
        const map = admin ? "byDocAdmin" : "byDoc";
        const { [viewKey(docId, admin)]: _gone, ...restErrors } = state.errors;
        commit({ [map]: { ...state[map], [docId]: data }, errors: restErrors } as Partial<ClaimsState>);
        return;
      } catch (e: any) {
        commit({ errors: { ...state.errors, [viewKey(docId, admin)]: e?.message || "Could not load the points of this circular." } });
        return;
      }
    }
  });
}

/** Reads again every copy of this circular the store holds. */
export function reloadDoc(docId: string): Promise<void> {
  const jobs: Promise<void>[] = [];
  if (state.byDoc[docId]) jobs.push(loadDoc(docId, false));
  if (state.byDocAdmin[docId]) jobs.push(loadDoc(docId, true));
  return Promise.all(jobs).then(() => undefined);
}

/** The number of points waiting, still being checked, and the circulars with nothing to show. */
export function loadCounts(): Promise<void> {
  return once("counts", async () => {
    for (let attempt = 0; attempt < 3; attempt++) {
      const started = epoch;
      try {
        const data = await fetchReviewCounts();
        if (started !== epoch) continue;
        commit({ counts: data, countsError: null });
        return;
      } catch (e: any) {
        commit({ countsError: e?.status === 403 ? null : "load" });
        return;
      }
    }
  });
}

function setQueue(queue: ReviewQueue, patch: Partial<QueueState>) {
  commit({ queue: { ...state.queue, [queue]: { ...state.queue[queue], ...patch } } });
}

/** Reads the first points of a queue. Points being decided right now are left out; points opened by a link stay. */
export function loadQueue(queue: ReviewQueue): Promise<void> {
  return once(`queue:${queue}`, async () => {
    if (!state.queue[queue].loaded) setQueue(queue, { loading: true });
    for (let attempt = 0; attempt < 3; attempt++) {
      const started = epoch;
      try {
        const data = await fetchReviewQueue(queue, null, 20);
        if (started !== epoch) continue;
        const cur = state.queue[queue];
        const gone = new Set(Object.keys(state.busy));
        const fresh = data.items.filter((r) => !gone.has(r.claim.id));
        const ids = new Set(fresh.map((r) => r.claim.id));
        const pinned = cur.pinned.filter((r) => !gone.has(r.claim.id) && !ids.has(r.claim.id));
        setQueue(queue, { items: [...pinned, ...fresh], pinned, next: data.next, total: data.total, loaded: true, loading: false, error: null });
        return;
      } catch (e: any) {
        setQueue(queue, { loading: false, error: e?.status === 403 ? "denied" : "load" });
        return;
      }
    }
    setQueue(queue, { loading: false });
  });
}

/** Reads the next group of points of a queue. */
export function loadMoreQueue(queue: ReviewQueue): Promise<void> {
  return once(`queue-more:${queue}`, async () => {
    const cur = state.queue[queue];
    if (!cur.next) return;
    try {
      const started = epoch;
      const data = await fetchReviewQueue(queue, cur.next, 20);
      if (started !== epoch) return;
      const have = new Set(state.queue[queue].items.map((r) => r.claim.id));
      const gone = new Set(Object.keys(state.busy));
      const more = data.items.filter((r) => !have.has(r.claim.id) && !gone.has(r.claim.id));
      setQueue(queue, { items: [...state.queue[queue].items, ...more], next: data.next, total: data.total });
    } catch {
      /* the next poll tries again */
    }
  });
}

/** Opens one point by its id (from a link on the circular page). Returns it, or null when it does not exist. */
export async function focusPoint(claimId: string): Promise<ReviewRow | null> {
  const present = [...state.queue.REQUIRED.items, ...state.queue.OPTIONAL.items].find((r) => r.claim.id === claimId);
  if (present) return present;
  try {
    const data = await fetchReviewPoint(claimId);
    const row = data.items[0];
    if (!row) return null;
    const open = ["WAITING_FOR_PERSON", "NOT_SHOWN", "CHECKING"].includes(row.claim.status ?? "");
    if (open) {
      const queue: ReviewQueue = row.claim.review_queue === "OPTIONAL" ? "OPTIONAL" : "REQUIRED";
      const cur = state.queue[queue];
      if (!cur.items.some((r) => r.claim.id === claimId)) setQueue(queue, { items: [row, ...cur.items], pinned: [row, ...cur.pinned] });
    }
    return row;
  } catch {
    return null;
  }
}

/** The page list of one file, fetched once. */
export function ensurePages(docId: string, versionId: string): Promise<void> {
  const key = `${docId}:${versionId}`;
  if (state.pageLists[key]) return Promise.resolve();
  return once(`pages:${key}`, async () => {
    try {
      const pages = await fetchDocumentPages(docId, versionId);
      commit({ pageLists: { ...state.pageLists, [key]: pages } });
    } catch {
      /* the screen asks again when it needs the pages */
    }
  });
}

/** A page that was saved from the page panel replaces its old copy at once. */
export function replacePage(docId: string, versionId: string, page: DocumentPage) {
  const key = `${docId}:${versionId}`;
  const list = state.pageLists[key];
  if (!list) return;
  commit({ pageLists: { ...state.pageLists, [key]: list.map((p) => (p.id === page.id ? page : p)) } });
}

/**
 * A person corrected a page: every point quoting it is checked again by the server at once, so the
 * circular, the review list and the links read their new state straight away (other tabs too).
 */
export function pageCorrected(docId: string, versionId: string | undefined, page: DocumentPage) {
  if (versionId) replacePage(docId, versionId, page);
  epoch++;
  void reloadDoc(docId);
  void refreshReview();
  void refreshLinks();
  broadcast(docId);
}

/** Starts fetching the page lists and page images of the next points, so moving on never waits. */
export function preloadAhead(queue: ReviewQueue, currentId: string | null, ahead = PRELOAD_AHEAD) {
  const items = state.queue[queue].items;
  const at = Math.max(0, items.findIndex((r) => r.claim.id === currentId));
  for (const row of items.slice(at, at + 1 + ahead)) {
    if (!row.version_id) continue;
    void ensurePages(row.circular.id, row.version_id);
    if (row.page) preloadPageImage(row.circular.id, row.version_id, row.page.page_number);
  }
  // Fetch the next group early, so the end of the list is never reached.
  if (items.length - at <= ahead + 2 && state.queue[queue].next) void loadMoreQueue(queue);
}

// ------------------------------------------------------------------------------------ other tabs

let channel: BroadcastChannel | null = null;
function getChannel(): BroadcastChannel | null {
  if (channel || typeof window === "undefined" || typeof BroadcastChannel === "undefined") return channel;
  channel = new BroadcastChannel("regwatch-claims");
  channel.onmessage = (e: MessageEvent) => {
    const docId = e?.data?.docId;
    if (typeof docId === "string") {
      void reloadDoc(docId);
      void refreshReview();
      void refreshLinks();
    }
  };
  return channel;
}

function broadcast(docId: string) {
  try {
    getChannel()?.postMessage({ docId });
  } catch {
    /* a closed channel only means other tabs wait for their next read */
  }
}

/** Reads the counts and, for a queue that was opened, its list again. */
export async function refreshReview() {
  const jobs: Promise<void>[] = [];
  if (state.counts) jobs.push(loadCounts());
  (["REQUIRED", "OPTIONAL"] as ReviewQueue[]).forEach((q) => {
    if (state.queue[q].loaded) jobs.push(loadQueue(q));
  });
  await Promise.all(jobs);
}

if (typeof window !== "undefined") {
  getChannel();
  // A link confirmed or rejected on the links screen changes its point: read the circular and the queue again.
  window.addEventListener("regwatch-link-decided", (e: Event) => {
    const docId = (e as CustomEvent).detail?.docId;
    if (typeof docId === "string") {
      epoch++;
      void reloadDoc(docId);
      void refreshReview();
      broadcast(docId);
    }
  });
  // Signing in or out changes what a person may see: start again.
  window.addEventListener(AUTH_CHANGED_EVENT, () => {
    epoch++;
    commit({
      byDoc: {},
      byDocAdmin: {},
      errors: {},
      notice: null,
      queue: { REQUIRED: emptyQueue(), OPTIONAL: emptyQueue() },
      counts: null,
      countsError: null,
      pageLists: {},
      reviewNotice: null,
    });
  });
}

// ------------------------------------------------------------------------------------ the screens' hooks

/**
 * The checked view of one circular. Loads it, keeps it fresh while the page is visible, and redraws
 * when anything changes it. `admin` asks for every point with its state (administrators only).
 */
export function useDocClaims(docId: string | null, admin: boolean): { view: CheckedView | undefined; error: string | undefined; loading: boolean; state: ClaimsState } {
  const s = useSyncExternalStore(subscribe, getClaimsState, getClaimsState);
  useEffect(() => {
    if (!docId) return;
    void loadDoc(docId, admin);
    let last = Date.now();
    const load = () => {
      last = Date.now();
      void loadDoc(docId, admin);
    };
    const changing = () => {
      const v = (admin ? getClaimsState().byDocAdmin : getClaimsState().byDoc)[docId];
      if (!v) return true;
      if (v.state === "ANALYSING") return true;
      const checking = v.counts?.checking ?? 0;
      return checking > 0 && !v.checking?.paused && !v.checking?.paused_until;
    };
    const tick = () => {
      if (typeof document !== "undefined" && document.visibilityState !== "visible") return;
      if (changing() || Date.now() - last >= IDLE_POLL_MS) load();
    };
    const wake = () => {
      if (typeof document !== "undefined" && document.visibilityState !== "visible") return;
      load();
    };
    const timer = window.setInterval(tick, POLL_MS);
    window.addEventListener("focus", wake);
    document.addEventListener("visibilitychange", wake);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", wake);
      document.removeEventListener("visibilitychange", wake);
    };
  }, [docId, admin]);
  const view = docId ? (admin ? s.byDocAdmin : s.byDoc)[docId] : undefined;
  const error = docId ? s.errors[viewKey(docId, admin)] : undefined;
  return { view, error, loading: !!docId && !view && !error, state: s };
}

/**
 * Keeps the review counts fresh for the admin console: every `everyMs` while the page is visible,
 * and again when the window gets focus. `queue` (when given) is read again with them.
 */
export function useReviewPolling(enabled: boolean, everyMs: number = REVIEW_POLL_MS, queue?: ReviewQueue) {
  useEffect(() => {
    if (!enabled) return;
    const tick = () => {
      if (typeof document !== "undefined" && document.visibilityState !== "visible") return;
      void loadCounts();
      if (queue) void loadQueue(queue);
    };
    tick();
    const timer = window.setInterval(tick, everyMs);
    window.addEventListener("focus", tick);
    document.addEventListener("visibilitychange", tick);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", tick);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [enabled, everyMs, queue]);
}

// ------------------------------------------------------------------------------------ hiding

function recount(sections: Record<ClaimSection, ClaimItem[]>, hidden: HiddenPoint[], admin: boolean): ClaimCounts {
  const out: ClaimCounts = { total: 0, shown: 0, checking: 0, waiting_for_team: 0, not_shown: 0 };
  for (const section of SECTIONS) {
    if (section === "clauses") continue;
    for (const it of sections[section] ?? []) {
      out.total++;
      if (!admin || it.shown) out.shown++;
      else if (it.status === "CHECKING") out.checking++;
      else if (it.status === "WAITING_FOR_PERSON") out.waiting_for_team++;
      else out.not_shown++;
    }
  }
  for (const h of hidden) {
    out.total++;
    if (h.state === "checking") out.checking++;
    else if (h.state === "waiting_for_team") out.waiting_for_team++;
    else out.not_shown++;
  }
  return out;
}

const SECTION_OF_KIND: Record<string, ClaimSection> = {
  SUMMARY_POINT: "summary",
  KEY_CHANGE: "changes",
  OBLIGATION: "requirements",
  APPLIES_TO: "applies_to",
  EXEMPTION: "exemptions",
  DATE: "dates",
  LINK: "links",
  PROVISION: "clauses",
};

// The fields a reader gets per kind (the server sends the same).
const READER_FIELDS: Record<string, string[]> = {
  SUMMARY_POINT: ["text"],
  KEY_CHANGE: ["text"],
  OBLIGATION: ["title", "description", "obligation_type", "who", "deadline", "effective_date", "frequency", "penalty", "clause"],
  APPLIES_TO: ["entity"],
  EXEMPTION: ["text"],
  DATE: ["date_kind", "date"],
  LINK: [],
  PROVISION: ["number", "heading", "explanation", "provision_type"],
};

const HIDDEN_STATE_OF: Record<string, HiddenPoint["state"]> = { CHECKING: "checking", WAITING_FOR_PERSON: "waiting_for_team", NOT_SHOWN: "not_shown" };

/** The same circular's views with these points hidden: held-back in the admin view, a plain line in the reader view. */
function hidePoints(s: ClaimsState, docId: string, ids: Set<string>): Pick<ClaimsState, "byDoc" | "byDocAdmin"> {
  const byDocAdmin = { ...s.byDocAdmin };
  const admin = s.byDocAdmin[docId];
  if (admin) {
    const sections = { ...admin.sections };
    for (const section of SECTIONS) {
      sections[section] = (admin.sections[section] ?? []).map((it) =>
        ids.has(it.id) ? { ...it, status: "WAITING_FOR_PERSON", shown: false, review_queue: "REQUIRED", why: ["A person asked for this point to be checked."] } : it
      );
    }
    byDocAdmin[docId] = { ...admin, sections, counts: recount(sections, [], true) };
  }
  const byDoc = { ...s.byDoc };
  const reader = s.byDoc[docId];
  if (reader) {
    const sections = { ...reader.sections };
    const hidden = [...reader.hidden];
    for (const section of SECTIONS) {
      sections[section] = (reader.sections[section] ?? []).filter((it) => {
        if (!ids.has(it.id)) return true;
        hidden.push({ section: (SECTION_OF_KIND[it.kind] ?? section) as ClaimSection, page_number: it.page_number, state: "waiting_for_team", quote_boxes: [] });
        return false;
      });
    }
    byDoc[docId] = { ...reader, sections, hidden, counts: recount(sections, hidden, false) };
  }
  return { byDoc, byDocAdmin };
}

function shownIds(view: CheckedView | undefined): string[] {
  if (!view) return [];
  const out: string[] = [];
  for (const section of SECTIONS) {
    if (section === "clauses") continue;
    for (const it of view.sections[section] ?? []) if (it.shown !== false) out.push(it.id);
  }
  return out;
}

async function afterChange(docId: string, hadLinks: boolean) {
  epoch++;
  broadcast(docId);
  await Promise.all([
    reloadDoc(docId),
    hadLinks ? loadStatus(docId).catch(() => undefined) : Promise.resolve(),
    hadLinks ? refreshLinks().catch(() => undefined) : Promise.resolve(),
    refreshReview(),
  ]);
}

/**
 * Hides one shown point until a person decides it. Every screen shows it hidden at once; the save
 * runs after, and everything is put back if it fails.
 */
export async function askReview(docId: string, claimId: string): Promise<boolean> {
  if (state.busy[claimId]) return false;
  const before = state;
  const item = (state.byDocAdmin[docId]?.sections ? SECTIONS.flatMap((sec) => state.byDocAdmin[docId].sections[sec] ?? []) : []).find((i) => i.id === claimId);
  epoch++;
  commit({ ...hidePoints(state, docId, new Set([claimId])), busy: { ...state.busy, [claimId]: true }, notice: null });
  try {
    await askReviewClaim(claimId);
    const { [claimId]: _done, ...rest } = state.busy;
    commit({ busy: rest });
    await afterChange(docId, item?.kind === "LINK");
    return true;
  } catch (e: any) {
    const { [claimId]: _failed, ...rest } = state.busy;
    const conflict = e?.status === 409;
    commit({
      byDoc: before.byDoc,
      byDocAdmin: before.byDocAdmin,
      busy: rest,
      notice: { kind: "error", text: conflict ? "That point was already hidden or decided by someone else." : "Could not hide that point. It is shown again." },
    });
    void reloadDoc(docId);
    return false;
  }
}

/** Hides every shown point of the circular until a person decides each one. */
export async function askReviewAll(docId: string): Promise<boolean> {
  if (state.busyDoc[docId]) return false;
  const before = state;
  const ids = new Set(shownIds(state.byDocAdmin[docId] ?? state.byDoc[docId]));
  if (ids.size === 0) return true;
  epoch++;
  commit({ ...hidePoints(state, docId, ids), busyDoc: { ...state.busyDoc, [docId]: true }, notice: null });
  try {
    await askReviewAllClaims(docId);
    const { [docId]: _done, ...rest } = state.busyDoc;
    commit({ busyDoc: rest });
    await afterChange(docId, true);
    return true;
  } catch {
    const { [docId]: _failed, ...rest } = state.busyDoc;
    commit({ byDoc: before.byDoc, byDocAdmin: before.byDocAdmin, busyDoc: rest, notice: { kind: "error", text: "Could not hide the points. They are shown again." } });
    void reloadDoc(docId);
    return false;
  }
}

// ------------------------------------------------------------------------------------ deciding

export type DecideResult =
  | { ok: true }
  | { ok: false; reason: "conflict" | "failed" }
  | { ok: false; reason: "problem"; problems: string[] };

/** The point as a reader would see it once it is shown. */
function readerItem(item: ClaimItem, action: ClaimAction): ClaimItem {
  const keep = READER_FIELDS[item.kind] ?? [];
  const fields: Record<string, any> = {};
  for (const k of keep) if (item.fields?.[k] !== undefined && item.fields?.[k] !== null && item.fields?.[k] !== "") fields[k] = item.fields[k];
  const out: ClaimItem = {
    id: item.id,
    kind: item.kind,
    fields,
    quote: item.quote,
    page_number: item.page_number,
    quote_boxes: item.quote_boxes,
    checked_by: "TEAM",
  };
  if (item.obligation_id) out.obligation_id = item.obligation_id;
  if (item.link) out.link = { ...item.link, shown_type: String(item.fields?.claimed_type ?? item.link.shown_type) };
  void action;
  return out;
}

/** The admin copy of a point after a decision, as the server will report it. */
function decidedItem(item: ClaimItem, action: ClaimAction, body: ClaimDecisionBody): ClaimItem {
  const fields = action === "fix" ? { ...item.fields, ...(body.fields ?? {}) } : { ...item.fields };
  const next: ClaimItem = { ...item, fields, status: action === "fix" ? "FIXED" : "APPROVED", shown: true, review_queue: null, why: [], checked_by: "TEAM" };
  if (item.kind === "LINK") {
    const claimed = String(fields.claimed_type ?? "REFERENCES");
    next.fields = { ...fields, shown_type: claimed };
    next.link = { target_document_id: item.link?.target_document_id ?? null, target_reference: item.link?.target_reference ?? null, shown_type: claimed };
  }
  return next;
}

function mapSections(view: CheckedView, fn: (it: ClaimItem) => ClaimItem | null): Record<ClaimSection, ClaimItem[]> {
  const sections = { ...view.sections };
  for (const section of SECTIONS) {
    sections[section] = (view.sections[section] ?? []).map(fn).filter((x): x is ClaimItem => x !== null);
  }
  return sections;
}

/** Both views of the circular with the decision shown. */
function showDecision(s: ClaimsState, docId: string, item: ClaimItem, action: ClaimAction | "reject", body: ClaimDecisionBody): Pick<ClaimsState, "byDoc" | "byDocAdmin"> {
  const byDocAdmin = { ...s.byDocAdmin };
  const admin = s.byDocAdmin[docId];
  if (admin) {
    const sections =
      action === "reject"
        ? mapSections(admin, (it) => (it.id === item.id ? null : it))
        : mapSections(admin, (it) => (it.id === item.id ? decidedItem(it, action, body) : it));
    byDocAdmin[docId] = { ...admin, sections, counts: recount(sections, [], true) };
  }
  const byDoc = { ...s.byDoc };
  const reader = s.byDoc[docId];
  if (reader) {
    const section = SECTION_OF_KIND[item.kind];
    let sections = { ...reader.sections };
    let hidden = [...reader.hidden];
    const inSection = (reader.sections[section] ?? []).some((it) => it.id === item.id);
    if (action === "reject") {
      if (inSection) sections = mapSections(reader, (it) => (it.id === item.id ? null : it));
      else hidden = dropHidden(hidden, item);
    } else if (inSection) {
      sections = mapSections(reader, (it) => (it.id === item.id ? readerItem(decidedItem(item, action, body), action) : it));
    } else if (section && section !== "clauses") {
      hidden = dropHidden(hidden, item);
      const added = readerItem(decidedItem(item, action, body), action);
      sections = { ...sections, [section]: [...(reader.sections[section] ?? []), added] };
    }
    byDoc[docId] = { ...reader, sections, hidden, counts: recount(sections, hidden, false) };
  }
  return { byDoc, byDocAdmin };
}

/** Removes the placeholder of one held point (the best match by section, page and state). */
function dropHidden(hidden: HiddenPoint[], item: ClaimItem): HiddenPoint[] {
  const section = SECTION_OF_KIND[item.kind];
  const wanted = HIDDEN_STATE_OF[item.status ?? ""];
  let at = hidden.findIndex((h) => h.section === section && h.page_number === item.page_number && h.state === wanted);
  if (at < 0) at = hidden.findIndex((h) => h.section === section && h.page_number === item.page_number);
  if (at < 0) at = hidden.findIndex((h) => h.section === section);
  return at < 0 ? hidden : hidden.filter((_h, i) => i !== at);
}

function findRow(claimId: string): { row: ReviewRow; queue: ReviewQueue; index: number } | null {
  for (const queue of ["REQUIRED", "OPTIONAL"] as ReviewQueue[]) {
    const index = state.queue[queue].items.findIndex((r) => r.claim.id === claimId);
    if (index >= 0) return { row: state.queue[queue].items[index], queue, index };
  }
  return null;
}

function findAdminItem(docId: string, claimId: string): ClaimItem | undefined {
  const view = state.byDocAdmin[docId];
  if (!view) return undefined;
  return SECTIONS.flatMap((sec) => view.sections[sec] ?? []).find((i) => i.id === claimId);
}

export interface DecideContext {
  /** The circular of the point, when it is not in the review queue. */
  docId?: string;
  /** The point, when it is not in the review queue. */
  claim?: ClaimItem;
  /** A link the links screens hold, so they show the decision too. */
  link?: RelLink;
}

/**
 * Approves, fixes or rejects one point. Every screen shows the result at once (the review screen moves
 * on, the counts drop, the circular page and the links view redraw); the save runs after. If the save
 * fails, the point comes back with a plain message. If somebody else decided it first, it stays gone
 * and the message says so.
 */
export async function decide(claimId: string, action: ClaimAction, body: ClaimDecisionBody = {}, ctx: DecideContext = {}): Promise<DecideResult> {
  if (state.busy[claimId]) return { ok: false, reason: "failed" };
  const found = findRow(claimId);
  const docId = found?.row.circular.id ?? ctx.docId;
  const item = found?.row.claim ?? ctx.claim ?? (docId ? findAdminItem(docId, claimId) : undefined);
  const before = state;
  epoch++;

  // 1. Show the decision everywhere, at once.
  const patch: Partial<ClaimsState> = { busy: { ...state.busy, [claimId]: true }, reviewNotice: null };
  if (found) {
    const cur = state.queue[found.queue];
    patch.queue = {
      ...state.queue,
      [found.queue]: { ...cur, items: cur.items.filter((r) => r.claim.id !== claimId), pinned: cur.pinned.filter((r) => r.claim.id !== claimId), total: Math.max(0, cur.total - 1) },
    };
  }
  if (state.counts) {
    const q = found?.queue ?? (item?.review_queue === "OPTIONAL" ? "OPTIONAL" : item?.review_queue === "REQUIRED" ? "REQUIRED" : null);
    if (q) patch.counts = { ...state.counts, required: Math.max(0, state.counts.required - (q === "REQUIRED" ? 1 : 0)), optional: Math.max(0, state.counts.optional - (q === "OPTIONAL" ? 1 : 0)) };
  }
  if (docId && item) Object.assign(patch, showDecision({ ...state, ...patch } as ClaimsState, docId, item, action, body));
  commit(patch);

  let undoLinks: (() => void) | null = null;
  const isLink = item?.kind === "LINK" || !!ctx.link;
  const relId = ctx.link?.id ?? (item?.kind === "LINK" ? item.relationship_id : undefined);
  if (relId && action !== "fix") undoLinks = showLinkDecision(relId, action === "approve" ? "VERIFIED" : "REJECTED", ctx.link);

  const putBack = () => {
    // The point returns to where it was, with its views as they were.
    const patchBack: Partial<ClaimsState> = {};
    if (found) {
      const cur = state.queue[found.queue];
      const items = [...cur.items];
      items.splice(Math.min(found.index, items.length), 0, found.row);
      patchBack.queue = { ...state.queue, [found.queue]: { ...cur, items, total: cur.total + 1 } };
    }
    if (state.counts && before.counts) patchBack.counts = before.counts;
    if (docId) {
      if (before.byDoc[docId]) patchBack.byDoc = { ...state.byDoc, [docId]: before.byDoc[docId] };
      if (before.byDocAdmin[docId]) patchBack.byDocAdmin = { ...state.byDocAdmin, [docId]: before.byDocAdmin[docId] };
    }
    undoLinks?.();
    commit(patchBack);
  };

  // 2. Save.
  try {
    const res = await decideClaim(claimId, action, body);
    const { [claimId]: _done, ...rest } = state.busy;
    const patchDone: Partial<ClaimsState> = { busy: rest };
    if (docId && state.byDocAdmin[docId]) {
      const view = state.byDocAdmin[docId];
      const sections = mapSections(view, (it) => (it.id === claimId ? { ...it, ...res.claim } : it));
      patchDone.byDocAdmin = { ...state.byDocAdmin, [docId]: { ...view, sections, counts: res.counts ?? view.counts } };
    }
    commit(patchDone);
    await afterChange(res.document_id || docId || "", isLink);
    return { ok: true };
  } catch (e: any) {
    const { [claimId]: _failed, ...rest } = state.busy;
    commit({ busy: rest });
    if (e instanceof ClaimDecisionError && e.status === 409) {
      // Somebody else decided it. It stays gone; show what they decided.
      commit({ reviewNotice: { kind: "info", text: REVIEW_TEXT.conflict, claimId } });
      if (docId && e.claim && state.byDocAdmin[docId]) {
        const view = state.byDocAdmin[docId];
        const sections = mapSections(view, (it) => (it.id === claimId ? { ...it, ...e.claim! } : it));
        commit({ byDocAdmin: { ...state.byDocAdmin, [docId]: { ...view, sections, counts: recount(sections, [], true) } } });
      }
      void afterChange(docId || "", isLink);
      return { ok: false, reason: "conflict" };
    }
    putBack();
    if (e instanceof ClaimDecisionError && e.status === 400 && e.problems.length > 0) {
      void refreshReview();
      return { ok: false, reason: "problem", problems: e.problems };
    }
    commit({ reviewNotice: { kind: "error", text: REVIEW_TEXT.saveFailed, claimId } });
    if (docId) void reloadDoc(docId);
    return { ok: false, reason: "failed" };
  }
}

/**
 * Confirms or rejects a link from the links screens. It is the same decision as on the review screen,
 * so both screens agree. A link with no checked point behind it (made before points existed) uses the
 * older link review.
 */
export async function decideLink(link: RelLink, decision: "VERIFIED" | "REJECTED"): Promise<boolean> {
  if (!link.claim_id) return reviewLink(link, decision);
  const result = await decide(link.claim_id, decision === "VERIFIED" ? "approve" : "reject", {}, { docId: link.source.id, link });
  if (result.ok) {
    setRelNotice({ kind: "success", text: decision === "VERIFIED" ? "Link confirmed. It now counts toward the in-force status." : "Link rejected. It is no longer shown." });
    return true;
  }
  setRelNotice({
    kind: "error",
    text: result.reason === "conflict" ? "Someone else already decided this link." : "Could not save that decision. Nothing was changed.",
  });
  commit({ reviewNotice: null });
  return false;
}
