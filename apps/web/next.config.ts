import type { NextConfig } from "next";

// Backend base URL. In dev/docker the browser talks to the web origin and this
// rewrite proxies /api/* to the API so the session cookie stays same-origin.
const API_BASE = process.env.API_PROXY_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API_BASE}/api/:path*` },
    ];
  },
};

export default nextConfig;
