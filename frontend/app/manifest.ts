import type { MetadataRoute } from "next";

/** Makes Amar Circular installable as an app on Android (and desktop): its own icon, full screen, no browser bar. */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Amar Circular",
    short_name: "Amar Circular",
    description: "Every Bangladesh Bank circular, checked and explained, with the page it came from.",
    start_url: "/",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#0e1311",
    theme_color: "#0e694d",
    categories: ["business", "finance", "productivity"],
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/maskable-192.png", sizes: "192x192", type: "image/png", purpose: "maskable" },
      { src: "/icons/maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
    shortcuts: [
      { name: "Read later", url: "/dashboard?box=later" },
      { name: "Search", url: "/search" },
    ],
  };
}
