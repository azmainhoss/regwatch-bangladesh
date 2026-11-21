"use client";

/**
 * One shared copy of the person's saved lists (Favourites, Read later, own lists).
 * Every star, bookmark, list menu and the Read later box on the home screen read from here, so a tap on one
 * shows on all of them at once. A tap changes the screen first and is saved in the background; if the save
 * fails, only that one change is put back. Other open tabs hear about it through a BroadcastChannel.
 */
import { useSyncExternalStore } from "react";
import { AUTH_CHANGED_EVENT, getStoredUser } from "./api";
import * as api from "./libraryApi";
import type { SavedList } from "./libraryApi";

export interface ListsState {
  userId: string | null;
  status: "idle" | "loading" | "ok" | "error";
  lists: SavedList[];
  /** Goes up on every change, so screens that show counts can re-read them. */
  version: number;
  error: string | null;
}

let state: ListsState = { userId: null, status: "idle", lists: [], version: 0, error: null };
const listeners = new Set<() => void>();
let channel: BroadcastChannel | null = null;
let inFlight = 0;

function set(next: Partial<ListsState>, broadcast = false) {
  state = { ...state, ...next };
  listeners.forEach((l) => l());
  if (broadcast && channel) channel.postMessage({ lists: state.lists, userId: state.userId });
}

function subscribe(l: () => void) {
  listeners.add(l);
  ensureStarted();
  return () => listeners.delete(l);
}

let started = false;
function ensureStarted() {
  if (started || typeof window === "undefined") return;
  started = true;
  try {
    channel = new BroadcastChannel("regwatch-lists");
    channel.onmessage = (e) => {
      if (e.data?.userId === state.userId) set({ lists: e.data.lists, version: state.version + 1 });
    };
  } catch {
    channel = null;
  }
  window.addEventListener(AUTH_CHANGED_EVENT, () => load(true));
  load();
}

export async function load(force = false) {
  const user = getStoredUser();
  const userId = user?.id ?? null;
  if (!userId) {
    set({ userId: null, status: "ok", lists: [], version: state.version + 1 });
    return;
  }
  if (!force && state.userId === userId && state.status !== "idle" && state.status !== "error") return;
  set({ userId, status: state.userId === userId ? state.status : "loading", ...(state.userId === userId ? {} : { lists: [] }) });
  try {
    const lists = await api.fetchLists();
    if (inFlight === 0 && getStoredUser()?.id === userId) set({ lists, status: "ok", error: null, version: state.version + 1 });
  } catch (e: any) {
    set({ status: "error", error: e?.message || "Could not load your lists." });
  }
}

export function useLists(): ListsState {
  return useSyncExternalStore(subscribe, () => state, () => state);
}

export function listOfKind(s: ListsState, kind: "FAVOURITES" | "READ_LATER"): SavedList | undefined {
  return s.lists.find((l) => l.kind === kind);
}

export function isIn(s: ListsState, listId: string | undefined, documentId: string): boolean {
  if (!listId) return false;
  return !!s.lists.find((l) => l.id === listId)?.document_ids.includes(documentId);
}

function applyLocal(listId: string, documentId: string, inList: boolean) {
  const lists = state.lists.map((l) =>
    l.id !== listId
      ? l
      : { ...l, document_ids: inList ? [documentId, ...l.document_ids.filter((d) => d !== documentId)] : l.document_ids.filter((d) => d !== documentId) },
  );
  set({ lists, version: state.version + 1 }, true);
}

/** Puts a circular in a list or takes it out. The screen changes at once; the save runs in the background. */
export async function toggle(listId: string, documentId: string, inList: boolean): Promise<void> {
  applyLocal(listId, documentId, inList);
  inFlight++;
  try {
    await api.setInList(listId, documentId, inList);
  } catch (e: any) {
    applyLocal(listId, documentId, !inList);
    set({ error: e?.message || "Could not save that change." });
  } finally {
    inFlight--;
    if (inFlight === 0) set({ version: state.version + 1 });
  }
}

export async function toggleKind(kind: "FAVOURITES" | "READ_LATER", documentId: string): Promise<void> {
  if (state.status !== "ok") await load(true);
  const l = listOfKind(state, kind);
  if (!l) return;
  return toggle(l.id, documentId, !l.document_ids.includes(documentId));
}

export async function createList(name: string, addDocumentId?: string): Promise<SavedList | undefined> {
  const before = new Set(state.lists.map((l) => l.id));
  const lists = await api.createList(name);
  set({ lists, version: state.version + 1 }, true);
  const made = lists.find((l) => !before.has(l.id));
  if (made && addDocumentId) await toggle(made.id, addDocumentId, true);
  return made;
}

export async function removeList(listId: string): Promise<void> {
  const lists = await api.deleteList(listId);
  set({ lists, version: state.version + 1 }, true);
}
