"use client";

/**
 * One shared copy of the circulars assigned to me and by me. The dashboard box and the assign dialog read
 * from here, so a new assignment or a "done" tick shows everywhere at once. Re-read when the tab is shown
 * again and every 30 seconds while it is visible, so work assigned by a colleague appears by itself.
 */
import { useSyncExternalStore } from "react";
import { AUTH_CHANGED_EVENT, getStoredUser } from "./api";
import * as api from "./shareApi";
import type { Assignment } from "./shareApi";

interface State {
  userId: string | null;
  items: Assignment[];
  loaded: boolean;
}

let state: State = { userId: null, items: [], loaded: false };
const listeners = new Set<() => void>();
let started = false;

function set(next: Partial<State>) {
  state = { ...state, ...next };
  listeners.forEach((l) => l());
}

export async function reloadAssignments() {
  const u = getStoredUser();
  if (!u) return set({ userId: null, items: [], loaded: true });
  try {
    const items = await api.fetchAssignments("all");
    if (getStoredUser()?.id === u.id) set({ userId: u.id, items, loaded: true });
  } catch {
    set({ loaded: true });
  }
}

function start() {
  if (started || typeof window === "undefined") return;
  started = true;
  reloadAssignments();
  window.addEventListener(AUTH_CHANGED_EVENT, reloadAssignments);
  document.addEventListener("visibilitychange", () => document.visibilityState === "visible" && reloadAssignments());
  window.setInterval(() => document.visibilityState === "visible" && reloadAssignments(), 30000);
}

export function useAssignments(): State {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      start();
      return () => listeners.delete(l);
    },
    () => state,
    () => state,
  );
}

export function addAssignments(items: Assignment[]) {
  set({ items: [...items, ...state.items.filter((i) => !items.some((n) => n.id === i.id))] });
}

export async function markAssignment(id: string, status: "OPEN" | "DONE") {
  const before = state.items;
  set({ items: state.items.map((i) => (i.id === id ? { ...i, status } : i)) });
  try {
    const saved = await api.setAssignmentStatus(id, status);
    set({ items: state.items.map((i) => (i.id === id ? saved : i)) });
  } catch {
    set({ items: before });
  }
}
