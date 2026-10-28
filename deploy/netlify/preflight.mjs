// Netlify build preflight: refuse to build the front end until netlify.toml points /api/* at a real https API origin.
// Runs from frontend/ (the Netlify base directory).
import { readFileSync } from "node:fs";

const toml = readFileSync(new URL("../../netlify.toml", import.meta.url), "utf8");
const m = toml.match(/from\s*=\s*"\/api\/\*"\s*\n\s*to\s*=\s*"([^"]+)"/);
const fail = (msg) => { console.error(`[netlify-preflight] ${msg}`); process.exit(1); };
if (!m) fail("netlify.toml has no /api/* proxy rule");
const target = m[1];
if (target.includes("PLACEHOLDER")) fail("replace API_ORIGIN_PLACEHOLDER in netlify.toml with the API host's https origin");
if (!target.startsWith("https://") || !target.endsWith("/:splat")) fail(`the /api/* target must be https://<api-host>/:splat, got ${target}`);
if (!process.env.PROXY_SIGNATURE_SECRET) console.warn("[netlify-preflight] PROXY_SIGNATURE_SECRET is not set on the site: the API will reject proxied requests if it requires a signature");
console.log(`[netlify-preflight] /api/* -> ${target}`);
