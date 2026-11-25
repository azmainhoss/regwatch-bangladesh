import type { MetadataRoute } from "next";
import { SITE_URL, serverApi } from "@/services/serverApi";
import { getHubs } from "@/services/publicApi";

// Built on request (not at build time, when the backend may be restarting); the circular list is cached an hour.
export const dynamic = "force-dynamic";

/** Home, the circular list pages (departments, subjects, years) and every indexable circular page. */
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const entries: MetadataRoute.Sitemap = [
    { url: `${SITE_URL}/`, changeFrequency: "daily", priority: 1 },
    { url: `${SITE_URL}/circulars`, changeFrequency: "daily", priority: 0.9 },
  ];
  try {
    const hubs = await getHubs();
    if (hubs) {
      for (const d of hubs.departments) entries.push({ url: `${SITE_URL}/circulars/${d.code}`, changeFrequency: "daily", priority: 0.8 });
      for (const t of hubs.topics) entries.push({ url: `${SITE_URL}/circulars/topic/${t.code}`, changeFrequency: "weekly", priority: 0.7 });
      for (const y of hubs.years) entries.push({ url: `${SITE_URL}/circulars/${y.code}`, changeFrequency: "weekly", priority: 0.6 });
    }
  } catch {
    /* backend unreachable: list pages are added on the next request */
  }
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
