// Offline lint for environments where ESLint / eslint-config-next cannot be installed.
// Uses the TypeScript compiler's own parser. It implements the rules from
// eslint-config-next ("next/core-web-vitals") that this codebase can trip,
// so a failing `next lint` is caught before CI:
//   react/no-unescaped-entities     ' " > } in JSX text                 (error)
//   react-hooks/rules-of-hooks      hooks only at the top level of components/hooks (error)
//   react/jsx-key                   elements returned from .map() need a key (error)
//   react-hooks/exhaustive-deps     effect/memo/callback deps list every local value used (warning -> fails here)
//   @next/next/no-img-element       <img> instead of next/image          (warning -> fails here)
//   @next/next/no-html-link-for-pages  <a href="/page"> instead of <Link> (error)
// It is NOT ESLint and does not replace `npm run lint` in CI. Every finding fails the run (no warnings allowed).
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const require = createRequire(import.meta.url);
const ts = (() => {
  for (const m of [process.env.TYPESCRIPT, "typescript", "/opt/npm-tools/node_modules/typescript"].filter(Boolean)) {
    try { return require(m); } catch { /* try the next location */ }
  }
  throw new Error("TypeScript not found; set TYPESCRIPT=/path/to/typescript");
})();

const files = [];
for (const dir of ["app", "components", "lib"]) {
  (function walk(d) {
    for (const e of fs.readdirSync(d, { withFileTypes: true })) {
      const p = path.join(d, e.name);
      if (e.isDirectory()) walk(p);
      else if (/\.(tsx?|jsx?)$/.test(e.name)) files.push(p);
    }
  })(path.join(root, dir));
}

const findings = [];
const report = (sf, node, rule, msg) => {
  const { line, character } = sf.getLineAndCharacterOfPosition(node.getStart(sf));
  findings.push(`${path.relative(root, sf.fileName)}:${line + 1}:${character + 1}  ${rule}  ${msg}`);
};
const isHookName = (n) => /^use[A-Z0-9]/.test(n);
const isComponentOrHook = (name) => !!name && (/^[A-Z]/.test(name) || isHookName(name));
const fnName = (fn) => {
  if ((ts.isFunctionDeclaration(fn) || ts.isFunctionExpression(fn)) && fn.name) return fn.name.text;
  const p = fn.parent;
  if (p && ts.isVariableDeclaration(p) && ts.isIdentifier(p.name)) return p.name.text;
  if (p && ts.isCallExpression(p) && p.parent && ts.isVariableDeclaration(p.parent) && ts.isIdentifier(p.parent.name)) return p.parent.name.text; // memo(() => ...)
  return null;
};
const isFn = (n) => ts.isFunctionDeclaration(n) || ts.isFunctionExpression(n) || ts.isArrowFunction(n) || ts.isMethodDeclaration(n);

// Values React guarantees stable: state setters, refs, dispatch from useReducer.
function stableNames(body) {
  const stable = new Set();
  const visit = (n) => {
    if (ts.isVariableDeclaration(n) && n.initializer && ts.isCallExpression(n.initializer) && ts.isIdentifier(n.initializer.expression)) {
      const callee = n.initializer.expression.text;
      if ((callee === "useState" || callee === "useReducer") && ts.isArrayBindingPattern(n.name) && n.name.elements[1]
          && ts.isBindingElement(n.name.elements[1]) && ts.isIdentifier(n.name.elements[1].name)) stable.add(n.name.elements[1].name.text);
      if (callee === "useRef" && ts.isIdentifier(n.name)) stable.add(n.name.text);
    }
    if (!isFn(n) || n === body) ts.forEachChild(n, visit);
  };
  visit(body);
  return stable;
}

// Names declared directly in a component/hook body (incl. params and destructuring).
function localNames(fn) {
  const names = new Set();
  const addBinding = (b) => {
    if (ts.isIdentifier(b)) names.add(b.text);
    else if (ts.isObjectBindingPattern(b) || ts.isArrayBindingPattern(b)) b.elements.forEach((e) => { if (ts.isBindingElement(e)) addBinding(e.name); });
  };
  fn.parameters.forEach((p) => addBinding(p.name));
  const visit = (n) => {
    if (ts.isVariableDeclaration(n)) addBinding(n.name);
    if (ts.isFunctionDeclaration(n) && n.name) names.add(n.name.text);
    if (!isFn(n)) ts.forEachChild(n, visit);
  };
  if (fn.body) ts.forEachChild(fn.body, visit);
  return names;
}

for (const file of files) {
  const text = fs.readFileSync(file, "utf8");
  const sf = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true, file.endsWith("x") ? ts.ScriptKind.TSX : ts.ScriptKind.TS);

  const visit = (node, ctx) => {
    // react/no-unescaped-entities
    if (ts.isJsxText(node)) {
      const m = node.text.match(/['">}]/);
      if (m) report(sf, node, "react/no-unescaped-entities", `\`${m[0]}\` must be escaped in JSX text (use &apos; &quot; &gt; &#125; or a {"…"} expression)`);
    }
    // @next/next/no-img-element and no-html-link-for-pages
    if (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) {
      const tag = node.tagName.getText(sf);
      if (tag === "img") report(sf, node, "@next/next/no-img-element", "use next/image instead of <img>");
      if (tag === "a") {
        const href = node.attributes.properties.find((p) => ts.isJsxAttribute(p) && p.name.getText(sf) === "href");
        const init = href && href.initializer;
        const lit = init && ts.isStringLiteral(init) ? init.text : null;
        if (lit && lit.startsWith("/") && !lit.startsWith("/api/")) report(sf, node, "@next/next/no-html-link-for-pages", `use <Link href="${lit}"> for internal pages`);
      }
    }
    // react/jsx-key: JSX returned from a .map() callback must carry key
    if (ts.isCallExpression(node) && ts.isPropertyAccessExpression(node.expression) && node.expression.name.text === "map") {
      const cb = node.arguments[0];
      if (cb && (ts.isArrowFunction(cb) || ts.isFunctionExpression(cb))) {
        const results = [];
        if (ts.isArrowFunction(cb) && !ts.isBlock(cb.body)) results.push(cb.body);
        else ts.forEachChild(cb.body, function f(n) { if (ts.isReturnStatement(n) && n.expression) results.push(n.expression); if (!isFn(n)) ts.forEachChild(n, f); });
        for (let r of results) {
          while (ts.isParenthesizedExpression(r)) r = r.expression;
          const el = ts.isJsxElement(r) ? r.openingElement : ts.isJsxSelfClosingElement(r) ? r : null;
          if (ts.isJsxFragment(r)) report(sf, r, "react/jsx-key", "a <>…</> fragment in a list cannot carry a key; use <Fragment key=…>");
          if (el && !el.attributes.properties.some((p) => ts.isJsxAttribute(p) && p.name.getText(sf) === "key"))
            report(sf, el, "react/jsx-key", "element in a .map() list is missing a key");
        }
      }
    }
    // react-hooks/rules-of-hooks
    if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && isHookName(node.expression.text)) {
      if (!ctx.owner) report(sf, node, "react-hooks/rules-of-hooks", `${node.expression.text} called outside a component or hook`);
      else if (ctx.conditional) report(sf, node, "react-hooks/rules-of-hooks", `${node.expression.text} called conditionally or in a loop`);
      else if (ctx.afterReturn) report(sf, node, "react-hooks/rules-of-hooks", `${node.expression.text} called after an early return`);
    }
    // react-hooks/exhaustive-deps
    if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && ["useEffect", "useLayoutEffect", "useCallback", "useMemo"].includes(node.expression.text)
        && ctx.owner && node.arguments.length === 2 && ts.isArrayLiteralExpression(node.arguments[1])) {
      const [cb, depsNode] = node.arguments;
      const deps = new Set(depsNode.elements.map((e) => e.getText(sf).split(/[.?]/)[0]));
      const locals = localNames(ctx.owner);
      const stable = stableNames(ctx.owner.body);
      const used = new Set();
      const shadow = new Set();
      (function collect(n) {
        if (ts.isTypeNode(n)) return;                    // type annotations/arguments are not runtime values
        if (ts.isVariableDeclaration(n) && ts.isIdentifier(n.name)) shadow.add(n.name.text);
        if (ts.isParameter(n) && ts.isIdentifier(n.name)) shadow.add(n.name.text);
        if (ts.isIdentifier(n) && !(ts.isPropertyAccessExpression(n.parent) && n.parent.name === n) && !(ts.isPropertyAssignment(n.parent) && n.parent.name === n)
            && !ts.isJsxAttribute(n.parent)) used.add(n.text);
        ts.forEachChild(n, collect);
      })(cb);
      for (const name of used) {
        if (locals.has(name) && !stable.has(name) && !shadow.has(name) && !deps.has(name))
          report(sf, node, "react-hooks/exhaustive-deps", `${node.expression.text} uses '${name}' but it is not in the dependency list`);
      }
    }

    // context for hook rules
    let next = ctx;
    if (isFn(node)) {
      // A component or hook starts a new hook scope; any other function (event handler, callback) is not one,
      // so a hook called inside it is reported as "outside a component or hook".
      next = isComponentOrHook(fnName(node)) ? { owner: node, conditional: false, afterReturn: false }
                                             : { owner: null, conditional: false, afterReturn: false };
    } else if (ts.isIfStatement(node) || ts.isConditionalExpression(node) || ts.isForStatement(node) || ts.isForOfStatement(node)
               || ts.isForInStatement(node) || ts.isWhileStatement(node) || ts.isDoStatement(node) || ts.isSwitchStatement(node)) {
      next = { ...ctx, conditional: true };
    } else if (ts.isBinaryExpression(node) && [ts.SyntaxKind.AmpersandAmpersandToken, ts.SyntaxKind.BarBarToken, ts.SyntaxKind.QuestionQuestionToken].includes(node.operatorToken.kind)) {
      visit(node.left, ctx);                                   // the left operand always runs
      visit(node.right, { ...ctx, conditional: true });        // the right operand may not
      return;
    }
    if (ts.isBlock(node) && ctx.owner && node.parent === ctx.owner) {
      // top-level statements of a component: a return inside an `if` makes later hooks conditional
      let returned = false;
      for (const st of node.statements) {
        visit(st, { ...next, afterReturn: returned });
        if (ts.isIfStatement(st) && containsReturn(st)) returned = true;
      }
      return;
    }
    ts.forEachChild(node, (c) => visit(c, next));
  };
  visit(sf, { owner: null, conditional: false, afterReturn: false });
}

function containsReturn(n) {
  let found = false;
  (function f(x) { if (ts.isReturnStatement(x)) found = true; if (!isFn(x) && !found) ts.forEachChild(x, f); })(n);
  return found;
}

for (const f of findings) console.log(f);
console.log(`[lint] ${files.length} files checked, ${findings.length} finding(s)`);
process.exit(findings.length ? 1 : 0);
