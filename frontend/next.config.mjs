/**
 * Same-origin routing: the browser only ever talks to this Next.js server.
 * /api/* is proxied to the FastAPI service, so the session cookie is
 * first-party (SameSite=Lax, HttpOnly, __Host- prefix in production) and no
 * CORS is needed. BACKEND_INTERNAL_URL is fixed at build time.
 */
const backend = process.env.BACKEND_INTERNAL_URL || "http://127.0.0.1:8000";

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Container image (frontend/Dockerfile) runs the standalone server. On Netlify (NETLIFY=true during its builds) the
  // OpenNext adapter packages the app itself, so the standalone output is left to it.
  output: process.env.NETLIFY ? undefined : "standalone",
  poweredByHeader: false,
  experimental: { proxyTimeout: 300000 },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/:path*` }];
  },
  async headers() {
    const security = [
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "X-Frame-Options", value: "DENY" },
      { key: "Referrer-Policy", value: "no-referrer" },
      { key: "Permissions-Policy", value: "geolocation=(), microphone=(), camera=()" },
    ];
    return [
      // App pages render no data on the server (all data is fetched after
      // login), but they are still never cached.
      { source: "/((?!_next/static|fonts|vecta-mark.png).*)", headers: [...security, { key: "Cache-Control", value: "no-store" }] },
      // The legacy service worker path must always be refetched so old
      // registrations pick up the self-unregistering replacement.
      { source: "/sw.js", headers: [{ key: "Cache-Control", value: "no-store, max-age=0" }] },
    ];
  },
};

export default nextConfig;
