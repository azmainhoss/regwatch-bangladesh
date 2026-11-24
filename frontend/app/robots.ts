import type { MetadataRoute } from "next";
import { SITE_URL } from "@/services/serverApi";

/** Public pages are open to crawlers; account, admin and API areas are not. */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: ["/", "/circular/"],
        disallow: ["/admin", "/workspace", "/alerts", "/api/", "/summary", "/compare"],
      },
    ],
    sitemap: `${SITE_URL}/sitemap.xml`,
    host: SITE_URL,
  };
}
