import type { MetadataRoute } from "next";
import { SITE_URL, serverApi } from "@/services/serverApi";

// Rebuilt at most once an hour.
export const revalidate = 3600;

/** Home and every indexable circular page (those with an AI verified analysis). */
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const entries: MetadataRoute.Sitemap = [{ url: `${SITE_URL}/`, changeFrequency: "daily", priority: 1 }];
  try {
    const res = await fetch(serverApi("/public/circulars/paths"), { next: { revalidate: 3600 } });
    if (res.ok) {
      const paths: { path: string; lastmod?: string | null }[] = await res.json();
      for (const p of paths) {
        entries.push({ url: `${SITE_URL}${p.path}`, lastModified: p.lastmod ?? undefined, changeFrequency: "monthly", priority: 0.7 });
      }
    }
  } catch {
    /* backend unreachable at build time: the home entry alone */
  }
  return entries;
}
