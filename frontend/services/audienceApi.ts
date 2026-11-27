"use client";
/** "For you": the reader's institution type, their "Applies to me" / "Not for me" marks, and the flag on each
 * circular (owner, 2026-11-28). Flags are cached here so the list and the circular page agree at once. */
import { useEffect, useState } from "react";
import { apiFetch, AUTH_CHANGED_EVENT, getStoredUser, throwApiError } from "./api";

export interface InstitutionKind {
  code: string;
  label: string;
  bank: boolean;
}
export interface Interest {
  tag: string;
  label: string;
  weight: number;
}
export interface AudienceMe {
  institution_type: string | null;
  institution_label: string | null;
  has_ad: boolean | null;
  source: "user" | "company" | "workspace" | null;
  company: string | null;
  interests: Interest[];
  not_interested: Interest[];
  kinds: InstitutionKind[];
}
export interface Flag {
  for_you: boolean;
  reason: string;
  mark: number;
  applies_to: string[];
}

export const AUDIENCE_CHANGED_EVENT = "amar-audience-changed";

const flags = new Map<string, Flag>();
const listeners = new Set<() => void>();
const notify = () => listeners.forEach((l) => l());

function announce() {
  flags.clear();
  notify();
  if (typeof window !== "undefined") window.dispatchEvent(new Event(AUDIENCE_CHANGED_EVENT));
}

async function ok<T>(res: Response, fallback: string): Promise<T> {
  if (!res.ok) await throwApiError(res, fallback);
  return res.json();
}

export async function fetchAudienceMe(): Promise<AudienceMe> {
  return ok(await apiFetch(`/audience/me`, { cache: "no-store" }), "Could not load your institution type.");
}

export async function fetchKinds(): Promise<InstitutionKind[]> {
  return ok(await apiFetch(`/audience/kinds`), "Could not load institution types.");
}

export async function guessInstitution(company: string): Promise<{ institution_type: string | null; has_ad: boolean | null }> {
  return ok(await apiFetch(`/audience/guess?company=${encodeURIComponent(company)}`), "Could not check the company.");
}

export async function saveInstitution(institution_type: string | null, has_ad: boolean | null): Promise<AudienceMe> {
  const me = await ok<AudienceMe>(
    await apiFetch(`/audience/me/profile`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ institution_type, has_ad }),
    }),
    "Could not save your institution type.",
  );
  announce();
  return me;
}

export async function muteInterest(tag: string, muted = true): Promise<AudienceMe> {
  const me = await ok<AudienceMe>(
    await apiFetch(`/audience/me/interests`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tag, muted }),
    }),
    "Could not update your interests.",
  );
  announce();
  return me;
}

export async function markCircular(documentId: string, value: -1 | 0 | 1): Promise<Flag> {
  const flag = await ok<Flag>(
    await apiFetch(`/audience/marks/${documentId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ value }),
    }),
    "Could not save that.",
  );
  // A mark can change similar circulars too: refresh every flag, with this one known at once.
  flags.clear();
  flags.set(documentId, flag);
  notify();
  if (typeof window !== "undefined") window.dispatchEvent(new Event(AUDIENCE_CHANGED_EVENT));
  return flag;
}

const pending = new Set<string>();
let timer: number | null = null;

function load(ids: string[]) {
  ids.filter((id) => !flags.has(id)).forEach((id) => pending.add(id));
  if (!pending.size || timer !== null) return;
  timer = window.setTimeout(async () => {
    timer = null;
    const batch = Array.from(pending).slice(0, 100);
    batch.forEach((id) => pending.delete(id));
    try {
      const res = await apiFetch(`/audience/flags?ids=${batch.join(",")}`, { cache: "no-store" });
      if (res.ok) {
        const data: Record<string, Flag> = await res.json();
        Object.entries(data).forEach(([id, f]) => flags.set(id, f));
        notify();
      }
    } catch {
      /* flags are extra: the list works without them */
    }
    if (pending.size) load([]);
  }, 30);
}

if (typeof window !== "undefined") {
  window.addEventListener(AUTH_CHANGED_EVENT, () => {
    flags.clear();
    notify();
  });
}

/** Flags for the circulars on screen (signed-in readers only). */
export function useFlags(ids: string[]): Record<string, Flag | undefined> {
  const [, setTick] = useState(0);
  const key = ids.join(",");
  useEffect(() => {
    const l = () => setTick((t) => t + 1);
    listeners.add(l);
    return () => {
      listeners.delete(l);
    };
  }, []);
  useEffect(() => {
    if (!getStoredUser() || !key) return;
    load(key.split(","));
  });
  const out: Record<string, Flag | undefined> = {};
  ids.forEach((id) => (out[id] = flags.get(id)));
  return out;
}

/** The reader's institution type and interests, re-read when they change anywhere. */
export function useAudienceMe(enabled: boolean): [AudienceMe | null, (m: AudienceMe) => void] {
  const [me, setMe] = useState<AudienceMe | null>(null);
  useEffect(() => {
    if (!enabled) {
      setMe(null);
      return;
    }
    let alive = true;
    const read = () =>
      fetchAudienceMe()
        .then((m) => alive && setMe(m))
        .catch(() => undefined);
    read();
    window.addEventListener(AUDIENCE_CHANGED_EVENT, read);
    return () => {
      alive = false;
      window.removeEventListener(AUDIENCE_CHANGED_EVENT, read);
    };
  }, [enabled]);
  return [me, setMe];
}
