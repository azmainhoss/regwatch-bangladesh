"use client";

/** Home screen feed, the numbers on its boxes, subject categories and saved lists. */
import { apiFetch, ApiError, type DocumentItem } from "./api";

async function json<T>(res: Response, fallback: string): Promise<T> {
  if (!res.ok) {
    let msg = fallback;
    try {
      const b = await res.json();
      if (typeof b?.detail === "string") msg = b.detail;
    } catch {
      /* keep the fallback */
    }
    throw new ApiError(res.status, msg);
  }
  return res.json();
}

export interface Choice {
  code: string;
  label: string;
  count: number;
}

export interface FeedCounts {
  today: number;
  week: number;
  month: number;
  read_later: number;
  favourites: number;
  library?: number;
  uncited_points?: number;
  departments: Choice[];
  topics: Choice[];
}

export interface FeedPage {
  total: number;
  items: DocumentItem[];
}

export type Period = "today" | "week" | "month";

export interface FeedQuery {
  period?: Period | null;
  department?: string | null;
  topic?: string | null;
  saved?: "READ_LATER" | "FAVOURITES" | null;
  list_id?: string | null;
  q?: string;
  limit?: number;
  offset?: number;
}

export async function fetchFeed(q: FeedQuery, signal?: AbortSignal): Promise<FeedPage> {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(q)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  return json(await apiFetch(`/feed?${p.toString()}`, { cache: "no-store", signal }), "Could not load circulars.");
}

export async function fetchFeedCounts(): Promise<FeedCounts> {
  return json(await apiFetch(`/feed/counts`, { cache: "no-store" }), "Could not load the numbers.");
}

export async function fetchTopicNames(): Promise<Choice[]> {
  return json(await apiFetch(`/feed/topics`), "Could not load categories.");
}

export interface SavedList {
  id: string;
  name: string;
  kind: "FAVOURITES" | "READ_LATER" | "CUSTOM";
  document_ids: string[];
}

export async function fetchLists(): Promise<SavedList[]> {
  return json(await apiFetch(`/me/lists`, { cache: "no-store" }), "Could not load your lists.");
}

export async function createList(name: string): Promise<SavedList[]> {
  return json(
    await apiFetch(`/me/lists`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) }),
    "Could not make the list.",
  );
}

export async function deleteList(listId: string): Promise<SavedList[]> {
  return json(await apiFetch(`/me/lists/${listId}`, { method: "DELETE" }), "Could not delete the list.");
}

export async function setInList(listId: string, documentId: string, inList: boolean): Promise<SavedList[]> {
  return json(
    await apiFetch(`/me/lists/${listId}/items/${documentId}`, { method: inList ? "PUT" : "DELETE" }),
    "Could not save that change.",
  );
}
