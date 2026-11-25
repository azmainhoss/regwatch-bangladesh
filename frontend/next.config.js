/** @type {import("next").NextConfig} */
const nextConfig = {
  // Produces .next/standalone, which infrastructure/docker/Dockerfile.frontend runs with `node server.js`.
  output: "standalone",
  // Visitor analytics (services/analytics.ts) is sent through our own domain so ad blockers do not drop it.
  async rewrites() {
    return [
      { source: "/ingest/static/:path*", destination: "https://us-assets.i.posthog.com/static/:path*" },
      { source: "/ingest/array/:path*", destination: "https://us-assets.i.posthog.com/array/:path*" },
      { source: "/ingest/:path*", destination: "https://us.i.posthog.com/:path*" },
    ];
  },
  skipTrailingSlashRedirect: true,
};

module.exports = nextConfig;
