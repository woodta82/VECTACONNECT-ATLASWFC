// Real ESLint (the CLI's engine, not a re-implementation) over every frontend source file, with ESLint's own
// recommended core rules. Used where npm is unreachable and eslint-config-next / typescript-eslint cannot be
// installed: each .ts/.tsx file is first transpiled by TypeScript (types erased, JSX kept), then linted by ESLint.
// React-hooks and Next.js rules are covered by verify/lint.mjs; CI runs `npm run lint` with eslint-config-next.
// Also covered here, because they were reported by `npm run lint` on a networked machine: unused disable directives
// (reportUnusedDisableDirectives), anonymous default exports (import/no-anonymous-default-export), and the
// verification shims and config files themselves.
//
//   ESLINT=/opt/node-tools/node_modules/eslint TYPESCRIPT=... node verify/eslint-core.mjs
import { createRequire } from "node:module";
import { mkdtempSync, readFileSync, readdirSync, statSync, writeFileSync, mkdirSync } from "node:fs";
import { join, relative, dirname } from "node:path";
import { tmpdir } from "node:os";

const require = createRequire(import.meta.url);
const load = (env, fallbacks) => {
  for (const p of [process.env[env], ...fallbacks].filter(Boolean)) {
    try { return require(p); } catch { /* next */ }
  }
  throw new Error(`cannot load ${fallbacks[0]}`);
};
const ts = load("TYPESCRIPT", ["typescript", "/opt/npm-tools/node_modules/typescript", "/opt/node-tools/node_modules/typescript"]);
const { ESLint } = load("ESLINT", ["eslint", "/opt/node-tools/node_modules/eslint"]);
const { builtinRules } = load("ESLINT_RISK", ["eslint/use-at-your-own-risk", "/opt/node-tools/node_modules/eslint/lib/unsupported-api.js"]);

const ROOT = new URL("..", import.meta.url).pathname;
const SKIP = new Set(["node_modules", ".next", "e2e", "public", "dist", ".gen"]);
function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    if (SKIP.has(name)) continue;
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (/\.(tsx?|mjs)$/.test(name) && !name.endsWith(".d.ts") && !(dir.endsWith("verify") && name !== "shims")) out.push(p);
  }
  return out;
}

const files = walk(ROOT);
const tmp = mkdtempSync(join(tmpdir(), "eslint-core-"));
const map = new Map();
for (const f of files) {
  const src = readFileSync(f, "utf8");
  const out = f.endsWith(".mjs") ? src : ts.transpileModule(src, {
    compilerOptions: { jsx: ts.JsxEmit.Preserve, target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext,
                       verbatimModuleSyntax: false, removeComments: false },
    fileName: f,
  }).outputText;
  const dest = join(tmp, relative(ROOT, f)).replace(/\.tsx?$/, (m) => (m === ".tsx" ? ".jsx" : ".js"));
  mkdirSync(dirname(dest), { recursive: true });
  writeFileSync(dest, out);
  map.set(dest, relative(ROOT, f));
}

const RULES = {
  "constructor-super": "error", "for-direction": "error", "getter-return": "error", "no-async-promise-executor": "error",
  "no-case-declarations": "error", "no-class-assign": "error", "no-compare-neg-zero": "error", "no-cond-assign": "error",
  "no-const-assign": "error", "no-constant-binary-expression": "error", "no-constant-condition": "error", "no-control-regex": "error",
  "no-debugger": "error", "no-delete-var": "error", "no-dupe-args": "error", "no-dupe-class-members": "error", "no-dupe-else-if": "error",
  "no-dupe-keys": "error", "no-duplicate-case": "error", "no-empty": ["error", { allowEmptyCatch: true }], "no-empty-character-class": "error",
  "no-empty-pattern": "error", "no-ex-assign": "error", "no-fallthrough": "error", "no-func-assign": "error", "no-global-assign": "error",
  "no-import-assign": "error", "no-invalid-regexp": "error", "no-irregular-whitespace": "error", "no-loss-of-precision": "error",
  "no-misleading-character-class": "error", "no-new-native-nonconstructor": "error", "no-nonoctal-decimal-escape": "error",
  "no-obj-calls": "error", "no-octal": "error", "no-prototype-builtins": "error", "no-redeclare": "error", "no-regex-spaces": "error",
  "no-self-assign": "error", "no-setter-return": "error", "no-shadow-restricted-names": "error", "no-sparse-arrays": "error",
  "no-this-before-super": "error", "no-unexpected-multiline": "error", "no-unreachable": "error", "no-unsafe-finally": "error",
  "no-unsafe-negation": "error", "no-unsafe-optional-chaining": "error", "no-unused-labels": "error", "no-unused-private-class-members": "error",
  "no-useless-backreference": "error", "no-useless-catch": "error", "no-useless-escape": "error", "no-with": "error",
  "require-yield": "error", "use-isnan": "error", "valid-typeof": "error",
};
// typescript-eslint's no-unused-vars (as configured by next/typescript) = ESLint's core rule on the type-erased code,
// with its defaults: no ignore patterns, destructured rest siblings NOT ignored, caught errors checked.
const UNUSED = ["error", { vars: "all", args: "after-used", ignoreRestSiblings: false, caughtErrors: "all" }];

// Minimal implementations of the two plugin rules this code base refers to, so their disable directives resolve and
// unused directives can be detected (the full plugins are installed in CI).
const nextPlugin = { rules: { "no-img-element": { meta: { type: "problem", schema: [] }, create: (ctx) => ({
  JSXOpeningElement(node) { if (node.name.type === "JSXIdentifier" && node.name.name === "img") ctx.report({ node, message: "Use next/image instead of <img>." }); },
}) } } };
const importPlugin = { rules: { "no-anonymous-default-export": { meta: { type: "suggestion", schema: [] }, create: (ctx) => ({
  ExportDefaultDeclaration(node) {
    const d = node.declaration;
    // eslint-plugin-import defaults: call expressions allowed; arrays, objects, arrow/anonymous functions, classes, literals, `new` not
    const anonymous = ["ArrayExpression", "ObjectExpression", "ArrowFunctionExpression", "Literal", "TemplateLiteral", "NewExpression"].includes(d.type)
      || ((d.type === "FunctionDeclaration" || d.type === "ClassDeclaration") && !d.id);
    if (anonymous) ctx.report({ node, message: "Assign the default export to a variable before exporting it (import/no-anonymous-default-export)." });
  },
}) } } };

const eslint = new ESLint({
  cwd: tmp,
  overrideConfigFile: true,
  overrideConfig: [{
    files: ["**/*.js", "**/*.jsx", "**/*.mjs"],
    languageOptions: { ecmaVersion: 2024, sourceType: "module", parserOptions: { ecmaFeatures: { jsx: true } } },
    linterOptions: { reportUnusedDisableDirectives: "error" },
    plugins: { "@next/next": nextPlugin, import: importPlugin, "@typescript-eslint": { rules: { "no-unused-vars": builtinRules.get("no-unused-vars") } } },
    rules: { ...RULES, "@typescript-eslint/no-unused-vars": UNUSED, "@next/next/no-img-element": "error",
             "import/no-anonymous-default-export": "error" },
  }],
});
const results = await eslint.lintFiles(["."]);
let problems = 0;
for (const r of results) {
  for (const m of r.messages) {
    problems += 1;
    console.log(`${map.get(r.filePath) ?? r.filePath}:${m.line}:${m.column}  ${m.severity === 2 ? "error" : "warning"}  ${m.message}  ${m.ruleId ?? ""}`);
  }
}
console.log(`[eslint-core] ESLint ${ESLint.version}: ${results.length} files (incl. verify/shims and config files), ${Object.keys(RULES).length} core rules + unused-directive, no-img-element and no-anonymous-default-export checks, ${problems} problem(s)`);
process.exit(problems ? 1 : 0);
