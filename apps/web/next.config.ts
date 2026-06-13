import type { NextConfig } from "next";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// CSP connect-src must include the FastAPI origin and WebSocket variants
const apiOrigin = API_BASE.replace(/^http/, "ws").replace(/^https/, "wss");
const apiHttpOrigin = API_BASE;

const ContentSecurityPolicy = [
  "default-src 'self'",
  // Next.js inline scripts + React hydration require 'unsafe-inline'
  // In production, swap for a nonce-based policy if needed
  "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https:",
  "font-src 'self'",
  `connect-src 'self' ${apiHttpOrigin} ${apiOrigin} wss: ws:`,
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
].join("; ");

const securityHeaders = [
  { key: "X-DNS-Prefetch-Control",   value: "on" },
  { key: "X-Content-Type-Options",   value: "nosniff" },
  { key: "X-Frame-Options",          value: "DENY" },
  { key: "X-XSS-Protection",         value: "1; mode=block" },
  { key: "Referrer-Policy",          value: "strict-origin-when-cross-origin" },
  {
    key:   "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), payment=(self)",
  },
  {
    key:   "Strict-Transport-Security",
    value: "max-age=63072000; includeSubDomains; preload",
  },
  { key: "Content-Security-Policy", value: ContentSecurityPolicy },
];

const nextConfig: NextConfig = {
  // Self-contained Node server (.next/standalone/server.js) for the Fly.io
  // container deploy — without this the Docker image can't run the app.
  output: "standalone",

  async headers() {
    return [{ source: "/(.*)", headers: securityHeaders }];
  },

  async rewrites() {
    return [
      { source: "/api/v1/:path*",   destination: `${API_BASE}/v1/:path*` },
      { source: "/mcp/v1/:path*",   destination: `${API_BASE}/mcp/v1/:path*` },
    ];
  },

  // Silence noisy peer-dependency warnings from Clerk / next-themes
  transpilePackages: [],
};

export default nextConfig;
