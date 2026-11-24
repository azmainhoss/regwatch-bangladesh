/**
 * Visitor access (owner, 2026-11-24):
 * - The first OPEN_DAYS days from a device's first visit are completely open: no meter, no register prompts.
 * - After that, FREE_LIMIT more circulars can be read in full; then any click asks them to register (free).
 * Read later, lists and assigning always need an account.
 * Opened circulars are counted on this device (localStorage). The circular the dashboard opens by itself before
 * the visitor has touched the page is not counted.
 */
export const OPEN_DAYS = 7;
export const FREE_LIMIT = 5;
export const FREE_VIEWS_EVENT = "amarcircular-free-views";
// v2: counts from the old "3 free circulars" rule do not carry over.
const KEY = "amarcircular_free_views_v2";
const FIRST_KEY = "amarcircular_first_visit";

/** When this device first visited (set on the first call). */
function firstVisit(): number {
  try {
    const v = parseInt(localStorage.getItem(FIRST_KEY) || "", 10);
    if (Number.isFinite(v) && v > 0) return v;
    const now = Date.now();
    localStorage.setItem(FIRST_KEY, String(now));
    return now;
  } catch {
    return Date.now();
  }
}

/** True during the first OPEN_DAYS days: everything is open and nothing is counted. */
export function inOpenPeriod(): boolean {
  if (typeof window === "undefined") return true;
  return Date.now() - firstVisit() < OPEN_DAYS * 24 * 60 * 60 * 1000;
}

let interacted = false;
if (typeof window !== "undefined") {
  const mark = () => {
    interacted = true;
  };
  window.addEventListener("pointerdown", mark, { capture: true, once: true });
  window.addEventListener("keydown", mark, { capture: true, once: true });
}

function read(): string[] {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) || "[]");
    return Array.isArray(v) ? v.filter((x) => typeof x === "string") : [];
  } catch {
    return [];
  }
}

function write(ids: string[]) {
  try {
    localStorage.setItem(KEY, JSON.stringify(ids));
  } catch {
    /* private mode: the count simply does not persist */
  }
  if (typeof window !== "undefined") window.dispatchEvent(new Event(FREE_VIEWS_EVENT));
}

export function viewedCount(): number {
  return read().length;
}

export function freeLeft(): number {
  if (inOpenPeriod()) return FREE_LIMIT;
  return Math.max(0, FREE_LIMIT - read().length);
}

export function freeExhausted(): boolean {
  return !inOpenPeriod() && read().length >= FREE_LIMIT;
}

/** True when this circular may be shown to a visitor: already counted, still within the limit, or opened by itself. */
export function canViewFree(docId: string): boolean {
  if (inOpenPeriod()) return true;
  const ids = read();
  return ids.includes(docId) || ids.length < FREE_LIMIT || !interacted;
}

/** Counts a circular the visitor opened (no-op for one already counted, or one opened before any interaction). */
export function countFreeView(docId: string): void {
  if (!interacted || inOpenPeriod()) return;
  const ids = read();
  if (ids.includes(docId) || ids.length >= FREE_LIMIT) return;
  write([...ids, docId]);
}
