"use client";

/** The signed-in person's plan and today's question count, shared by every screen. */
import { useSyncExternalStore } from "react";
import { apiFetch, AUTH_CHANGED_EVENT, getStoredUser } from "./api";

export interface PlanInfo {
  code: string;
  name: string;
  price_bdt_month: number;
  per: string;
  min_seats: number;
  questions_per_day: number;
  features: string[];
}

export interface MyPlan {
  plan: "FREE" | "PRO" | "ENTERPRISE";
  name: string;
  via_organization: boolean;
  questions_today: number;
  questions_per_day: number;
  allows: string[];
  pending_request?: string | null;
}

interface State {
  me: MyPlan | null;
  plans: PlanInfo[];
}

let state: State = { me: null, plans: [] };
const listeners = new Set<() => void>();
let started = false;

function set(next: Partial<State>) {
  state = { ...state, ...next };
  listeners.forEach((l) => l());
}

export async function reloadPlan() {
  if (!getStoredUser()) return set({ me: null });
  try {
    const r = await apiFetch("/plans/me", { cache: "no-store" });
    if (r.ok) set({ me: await r.json() });
  } catch {
    /* keep the last copy */
  }
}

async function loadPlans() {
  try {
    const r = await apiFetch("/plans");
    if (r.ok) set({ plans: await r.json() });
  } catch {
    /* the page shows a retry */
  }
}

function start() {
  if (started || typeof window === "undefined") return;
  started = true;
  reloadPlan();
  loadPlans();
  window.addEventListener(AUTH_CHANGED_EVENT, reloadPlan);
}

export function usePlan(): State {
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

/** True when the person may use a feature. Signed-out people and Free get false for paid features. */
export function canUse(s: State, feature: string): boolean {
  return !!s.me?.allows.includes(feature);
}

/** Counts one question at once on screen (the server counts it too). */
export function noteQuestionAsked() {
  if (state.me) set({ me: { ...state.me, questions_today: state.me.questions_today + 1 } });
}

export async function requestUpgrade(body: { plan: "PRO" | "ENTERPRISE"; seats?: number; organization_name?: string; contact_phone?: string; note?: string }) {
  const r = await apiFetch("/plans/request", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const b = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof b?.detail === "string" ? b.detail : "Could not send the request.");
  set({ me: b });
  return b as MyPlan;
}
