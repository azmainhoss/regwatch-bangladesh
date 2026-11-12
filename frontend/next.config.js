/** @type {import("next").NextConfig} */
const nextConfig = {
  // Produces .next/standalone, which infrastructure/docker/Dockerfile.frontend runs with `node server.js`.
  output: "standalone",
};

module.exports = nextConfig;
