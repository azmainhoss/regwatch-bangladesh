/**
 * Server-side calls to the backend (server components, sitemap). On the server the backend is reached directly on
 * the same machine; INTERNAL_API_URL overrides it (for example in development with another port).
 */
export const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL || "https://amarcircular.com").replace(/\/+$/, "");

export function serverApi(path: string): string {
  const base = (process.env.INTERNAL_API_URL || "http://127.0.0.1:8000/api/v1").replace(/\/+$/, "");
  return `${base}${path.startsWith("/") ? path : `/${path}`}`;
}
