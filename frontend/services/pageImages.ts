"use client";

import { fetchPageImage } from "./api";

// Page images already fetched, as object URLs. Kept small; the oldest is released first.
const imageCache = new Map<string, Promise<string>>();
// The same images once they have arrived, so a screen can draw one in the same frame (no spinner).
const ready = new Map<string, string>();
const IMAGE_CACHE_LIMIT = 24;

const keyOf = (documentId: string, versionId: string, pageNo: number, dpi: number) => `${documentId}:${versionId}:${pageNo}:${dpi}`;

export const DEFAULT_PAGE_DPI = 144;

export function loadPageImage(documentId: string, versionId: string, pageNo: number, dpi: number = DEFAULT_PAGE_DPI): Promise<string> {
  const key = keyOf(documentId, versionId, pageNo, dpi);
  const hit = imageCache.get(key);
  if (hit) {
    imageCache.delete(key);
    imageCache.set(key, hit);
    return hit;
  }
  const p = fetchPageImage(documentId, versionId, pageNo, dpi);
  p.then((url) => ready.set(key, url)).catch(() => {
    imageCache.delete(key);
    ready.delete(key);
  });
  imageCache.set(key, p);
  while (imageCache.size > IMAGE_CACHE_LIMIT) {
    const oldest = imageCache.keys().next().value as string;
    imageCache.get(oldest)?.then((url) => URL.revokeObjectURL(url)).catch(() => undefined);
    imageCache.delete(oldest);
    ready.delete(oldest);
  }
  return p;
}

/** The image if it has already arrived. */
export function peekPageImage(documentId: string, versionId: string, pageNo: number, dpi: number = DEFAULT_PAGE_DPI): string | null {
  return ready.get(keyOf(documentId, versionId, pageNo, dpi)) ?? null;
}

/** Starts fetching a page image in the background. Never throws. */
export function preloadPageImage(documentId: string, versionId: string, pageNo: number, dpi: number = DEFAULT_PAGE_DPI): void {
  loadPageImage(documentId, versionId, pageNo, dpi).catch(() => undefined);
}
