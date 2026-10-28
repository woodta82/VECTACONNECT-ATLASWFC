// Verification server: serves verify/dist and proxies /api/* to the backend with
// the /api prefix removed (the same contract as next.config.mjs rewrites).
// Adds the security headers next.config.mjs sets. Not a production server.
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const dist = path.join(path.dirname(fileURLToPath(import.meta.url)), "dist");
const backend = new URL(process.env.BACKEND || "http://127.0.0.1:8000");
const port = Number(process.env.PORT || 3000);
const TYPES = { ".js": "text/javascript", ".css": "text/css", ".html": "text/html; charset=utf-8", ".png": "image/png", ".ttf": "font/ttf",
                ".json": "application/json", ".map": "application/json" };
const SECURITY = { "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
                   "Permissions-Policy": "geolocation=(), microphone=(), camera=()" };

http.createServer((req, res) => {
  if (req.url.startsWith("/api/") || req.url === "/api") {
    const target = req.url.replace(/^\/api/, "") || "/";
    const headers = { ...req.headers, host: backend.host };
    const p = http.request({ hostname: backend.hostname, port: backend.port, path: target, method: req.method, headers }, (r) => {
      res.writeHead(r.statusCode || 502, r.headers);
      r.pipe(res);
    });
    p.on("error", () => { res.writeHead(502, { "content-type": "application/json" }); res.end('{"error":{"code":"bad_gateway","detail":"backend unreachable"}}'); });
    req.pipe(p);
    return;
  }
  const clean = decodeURIComponent(req.url.split("?")[0]);
  let file = path.join(dist, clean);
  if (!file.startsWith(dist) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) file = path.join(dist, "index.html");
  const ext = path.extname(file);
  res.writeHead(200, { "content-type": TYPES[ext] || "application/octet-stream", ...SECURITY,
                       "cache-control": ext === ".html" || ext === ".js" ? "no-store" : "public, max-age=3600" });
  fs.createReadStream(file).pipe(res);
}).listen(port, process.env.HOST || "127.0.0.1", () => console.log(`[verify] serving ${dist} on http://${process.env.HOST || "127.0.0.1"}:${port}, /api -> ${backend.href}`));
