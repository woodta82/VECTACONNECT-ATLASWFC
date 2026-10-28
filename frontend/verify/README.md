# Frontend verification harness (NOT the production build)

The production frontend is the Next.js App Router application in `../app`, built with
`npm ci && npm run build` (see `../package.json`, `../Dockerfile`). The build environment
used for the 26 October 2026 directive could not reach the npm registry, so Next.js
itself could not be installed or built there.

To still execute the real page components in a real browser, this harness:

- type-checks every page and component with the real TypeScript compiler against the real
  `@types/react` / `@types/react-dom` definitions (DefinitelyTyped), with `next/link`,
  `next/navigation`, `next` (types only) and `lucide-react` resolved to the small stand-ins
  in `shims/`;
- bundles the same `app/**/page.tsx` files with esbuild and real React 19 into a single-page
  app whose router maps URLs to those pages exactly as the App Router does
  (`app/x/[id]/page.tsx` -> `/x/:id`), wrapped in the real root layout's `AuthShell`;
- serves the bundle and proxies `/api/*` to the FastAPI backend, as `next.config.mjs` does.

What this does NOT verify: Next.js compilation, server rendering, `next.config.mjs` headers,
or the `next build` output. Those run in CI (`.github/workflows/ci.yml`) where npm is available.

Usage (paths default to the build environment; override with env vars):

    JS_DEPS=/opt/npm-tools/node_modules DT=/home/claude/vendor-js/dt/types \
    CSSTYPE=/home/claude/vendor-js/csstype LUCIDE=/home/claude/vendor-js/lucide/icons \
    POPPINS=/home/claude/vendor-js/poppins node verify/build.mjs          # icons, routes, typecheck, bundle
    BACKEND=http://127.0.0.1:8000 PORT=3000 node verify/server.mjs        # serve + proxy /api
