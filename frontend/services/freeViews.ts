/**
 * Visitors who have not registered may read FREE_LIMIT circulars in full. Opened circulars are counted on this
 * device (localStorage); after that, any click asks them to register. The circular the dashboard opens by itself
 * before the visitor has touched the page is not counted.
 */
export const FREE_LIMIT = 3;
export const FREE_VIEWS_EVENT = "amarcircular-free-views";
const KEY = "amarcircular_free_views";

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
  return Math.max(0, FREE_LIMIT - read().length);
}

export function freeExhausted(): boolean {
  return read().length >= FREE_LIMIT;
}

/** True when this circular may be shown to a visitor: already counted, still within the limit, or opened by itself. */
export function canViewFree(docId: string): boolean {
  const ids = read();
  return ids.includes(docId) || ids.length < FREE_LIMIT || !interacted;
}

/** Counts a circular the visitor opened (no-op for one already counted, or one opened before any interaction). */
export function countFreeView(docId: string): void {
  if (!interacted) return;
  const ids = read();
  if (ids.includes(docId) || ids.length >= FREE_LIMIT) return;
  write([...ids, docId]);
}
