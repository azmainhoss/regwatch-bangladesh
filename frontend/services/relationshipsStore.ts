"use client";

/**
 * One shared copy of everything the screens know about links between circulars: in-force
 * status, history, graph and the admin review list. Every screen reads from here, so a decision
 * saved on one screen (approving a link) shows on all of them in the same moment: the list row
 * badge, the circular's header, its history and graph, and the admin list. A decision is shown at
 * once, saved in the background, and put back (with an error message) if saving fails.
 */
import { useSyncExternalStore } from "react";
import {
  DocumentItem,
  DocumentRef,
  PendingLinks,
  RelGraph,
  RelLink,
  RelStatus,
  RelTimeline,
  fetchPendingLinks,
  fetchRelGraph,
  fetchRelStatus,
  fetchRelTimeline,
  reviewRelationship,
} from "./api";

export type Decision = "VERIFIED" | "REJECTED";

/** What a link of each type does to the circular it points at (only once confirmed). */
export const TYPE_STATUS: Record<string, string> = { AMENDS: "AMENDED", SUPERSEDES: "REPLACED", REPLACES: "REPLACED", REPEALS: "REPEALED" };
const SUCCESSOR_TYPES = new Set(["SUPERSEDES", "REPLACES", "REPEALS"]);
const RANK: Record<string, number> = { IN_FORCE: 0, AMENDED: 1, REPLACED: 2, REPEALED: 3 };

export interface InForceInfo {
  status: string;
  byId?: string | null;
  byRef?: string | null;
}

export interface RelState {
  /** In-force status of every circular seen so far, by document id. */
  inForce: Record<string, InForceInfo>;
  status: Record<string, RelStatus>;
  /** Keyed "<document id>:<depth>". */
  graph: Record<string, RelGraph>;
  timeline: Record<string, RelTimeline>;
  pending: PendingLinks | null;
  pendingError: string | null;
  /** Links whose decision is being saved. */
  busy: Record<string, Decision>;
  notice: { kind: "error" | "success"; text: string } | null;
}

let state: RelState = { inForce: {}, status: {}, graph: {}, timeline: {}, pending: null, pendingError: null, busy: {}, notice: null };
// Counts decisions; an answer fetched before the latest decision is thrown away and fetched again.
let epoch = 0;
const listeners = new Set<() => void>();

function commit(next: Partial<RelState> | RelState) {
  state = { ...state, ...next };
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function getRelState() {
  return state;
}

export function useRelState(): RelState {
  return useSyncExternalStore(subscribe, getRelState, getRelState);
}

/** The in-force info for a circular: the freshest copy in the store, else what the list sent. */
export function inForceOf(s: RelState, doc: Pick<DocumentItem, "id" | "in_force_status" | "in_force_by_id" | "in_force_by_reference">): InForceInfo | undefined {
  return s.inForce[doc.id] ?? (doc.in_force_status ? { status: doc.in_force_status, byId: doc.in_force_by_id, byRef: doc.in_force_by_reference } : undefined);
}

export function clearNotice() {
  commit({ notice: null });
}

/** Puts the in-force status the list or detail endpoint sent into the store. */
export function seedDocuments(docs: DocumentItem[]) {
  // While a decision is being saved, a list fetched before it must not put the old badge back.
  if (Object.keys(state.busy).length > 0) return;
  const next = { ...state.inForce };
  let changed = false;
  for (const d of docs) {
    if (!d.in_force_status) continue;
    const cur = next[d.id];
    if (cur && cur.status === d.in_force_status && cur.byId === d.in_force_by_id) continue;
    next[d.id] = { status: d.in_force_status, byId: d.in_force_by_id, byRef: d.in_force_by_reference };
    changed = true;
  }
  if (changed) commit({ inForce: next });
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

async function guarded<T>(fetcher: () => Promise<T>, store: (data: T) => void): Promise<void> {
  for (let attempt = 0; attempt < 3; attempt++) {
    const started = epoch;
    const data = await fetcher();
    if (started === epoch) {
      store(data);
      return;
    }
  }
}

export function loadStatus(id: string): Promise<void> {
  return once(`status:${id}`, () =>
    guarded(
      () => fetchRelStatus(id),
      (data) => {
        const inForce = { ...state.inForce, [id]: { status: data.in_force_status, byId: data.in_force_by?.id ?? null, byRef: data.in_force_by?.reference_number ?? null } };
        commit({ status: { ...state.status, [id]: data }, inForce });
      }
    )
  );
}

export function loadGraph(id: string, depth = 2): Promise<void> {
  return once(`graph:${id}:${depth}`, () =>
    guarded(
      () => fetchRelGraph(id, depth),
      (data) => commit({ graph: { ...state.graph, [`${id}:${depth}`]: data } })
    )
  );
}

export function loadTimeline(id: string): Promise<void> {
  return once(`timeline:${id}`, () =>
    guarded(
      () => fetchRelTimeline(id),
      (data) => commit({ timeline: { ...state.timeline, [id]: data } })
    )
  );
}

export function loadPending(): Promise<void> {
  return once("pending", async () => {
    try {
      await guarded(
        () => fetchPendingLinks(200),
        (data) => commit({ pending: data, pendingError: null })
      );
    } catch (e: any) {
      commit({ pendingError: e?.message || "Could not load the links awaiting review." });
    }
  });
}

/** Fetches everything the store holds again, so what is shown matches the server. */
export async function refreshAll() {
  const jobs: Promise<unknown>[] = [];
  Object.keys(state.status).forEach((id) => jobs.push(loadStatus(id).catch(() => undefined)));
  Object.keys(state.graph).forEach((k) => {
    const [id, depth] = k.split(":");
    jobs.push(loadGraph(id, Number(depth)).catch(() => undefined));
  });
  Object.keys(state.timeline).forEach((id) => jobs.push(loadTimeline(id).catch(() => undefined)));
  if (state.pending) jobs.push(loadPending());
  await Promise.all(jobs);
}

// ------------------------------------------------------------------------------------ deciding

function applyDecision(s: RelState, link: RelLink, decision: Decision): RelState {
  const typeStatus = TYPE_STATUS[link.relationship_type];
  const targetId = link.target?.id;
  let newInfo: InForceInfo | undefined;
  if (decision === "VERIFIED" && typeStatus && targetId && targetId !== link.source.id) {
    const current = s.inForce[targetId]?.status ?? s.status[targetId]?.in_force_status ?? link.target?.in_force_status ?? "IN_FORCE";
    if ((RANK[typeStatus] ?? 0) >= (RANK[current] ?? 0)) {
      newInfo = { status: typeStatus, byId: link.source.id, byRef: link.source.reference_number };
    }
  }

  const patchRef = (ref: DocumentRef): DocumentRef => (newInfo && ref.id === targetId ? { ...ref, in_force_status: newInfo.status } : ref);
  const mapLink = (l: RelLink): RelLink => ({
    ...l,
    verification_status: l.id === link.id ? decision : l.verification_status,
    source: patchRef(l.source),
    target: l.target ? patchRef(l.target) : l.target,
  });

  const status: Record<string, RelStatus> = {};
  for (const [id, st] of Object.entries(s.status)) {
    const wasPending = st.unconfirmed_incoming.some((l) => l.id === link.id);
    let verified = st.verified_incoming.map(mapLink);
    if (wasPending && decision === "VERIFIED") verified = [...verified, mapLink(link)];
    const own = id === targetId && newInfo;
    status[id] = {
      ...st,
      in_force_status: own ? newInfo!.status : st.in_force_status,
      in_force_by: own ? patchRef(link.source) : st.in_force_by,
      current_version: own && SUCCESSOR_TYPES.has(link.relationship_type) ? patchRef(link.source) : st.current_version ? patchRef(st.current_version) : st.current_version,
      verified_incoming: verified,
      unconfirmed_incoming: st.unconfirmed_incoming.filter((l) => l.id !== link.id).map(mapLink),
      outgoing: st.outgoing.filter((l) => !(l.id === link.id && decision === "REJECTED")).map(mapLink),
    };
  }

  const graph: Record<string, RelGraph> = {};
  for (const [key, g] of Object.entries(s.graph)) {
    const edges = g.edges.filter((e) => !(e.id === link.id && decision === "REJECTED")).map((e) => (e.id === link.id ? { ...e, verification_status: decision } : e));
    const used = new Set(edges.flatMap((e) => [e.source, e.target]));
    const nodes = g.nodes
      .filter((n) => n.in_library || n.is_center || used.has(n.key))
      .map((n) => (newInfo && n.document_id === targetId ? { ...n, in_force_status: newInfo.status } : n));
    graph[key] = { ...g, edges, nodes };
  }

  const timeline: Record<string, RelTimeline> = {};
  for (const [id, t] of Object.entries(s.timeline)) {
    const own = id === targetId && newInfo;
    const items = t.items.map((it) => ({
      ...it,
      document: patchRef(it.document),
      changes: it.changes.filter((l) => !(l.id === link.id && decision === "REJECTED")).map(mapLink),
    }));
    timeline[id] = {
      ...t,
      in_force_status: own ? newInfo!.status : t.in_force_status,
      in_force_by: own ? patchRef(link.source) : t.in_force_by,
      has_unconfirmed: items.some((it) => it.changes.some((l) => l.verification_status === "PENDING_REVIEW")),
      items,
    };
  }

  const pending = s.pending
    ? { ...s.pending, total: Math.max(0, s.pending.total - (s.pending.links.some((l) => l.id === link.id) ? 1 : 0)), links: s.pending.links.filter((l) => l.id !== link.id) }
    : s.pending;

  return { ...s, inForce: newInfo && targetId ? { ...s.inForce, [targetId]: newInfo } : s.inForce, status, graph, timeline, pending };
}

/**
 * Confirms or rejects a link. Every screen shows the result at once; the decision is saved in the
 * background, and everything is put back if the save fails.
 */
export async function reviewLink(link: RelLink, decision: Decision): Promise<boolean> {
  if (state.busy[link.id]) return false;
  const before = state;
  epoch++;
  commit({ ...applyDecision(state, link, decision), busy: { ...state.busy, [link.id]: decision }, notice: null });
  try {
    const res = await reviewRelationship(link.id, decision);
    const { [link.id]: _done, ...rest } = state.busy;
    const inForce = { ...state.inForce };
    const targetId = link.target?.id;
    if (targetId && res.target_in_force_status && inForce[targetId] && inForce[targetId].status !== res.target_in_force_status) {
      inForce[targetId] = { status: res.target_in_force_status };
    }
    commit({
      busy: rest,
      inForce,
      notice: { kind: "success", text: decision === "VERIFIED" ? "Link confirmed. It now counts toward the in-force status." : "Link rejected. It is no longer shown." },
    });
    void refreshAll();
    return true;
  } catch (e: any) {
    const { [link.id]: _failed, ...rest } = state.busy;
    commit({ ...before, busy: rest, notice: { kind: "error", text: `Could not save that decision: ${e?.message || "unknown error"}. Nothing was changed.` } });
    void refreshAll();
    return false;
  }
}
