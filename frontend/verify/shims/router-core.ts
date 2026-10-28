// Minimal App Router stand-in: location state shared by Link and the navigation hooks.
import { useSyncExternalStore } from "react";

const listeners = new Set<() => void>();
function emit() { listeners.forEach((l) => l()); }
if (typeof window !== "undefined") window.addEventListener("popstate", emit);

export function navigate(href: string, replace = false) {
  if (replace) window.history.replaceState(null, "", href); else window.history.pushState(null, "", href);
  window.scrollTo(0, 0);
  emit();
}

function subscribe(l: () => void) { listeners.add(l); return () => { listeners.delete(l); }; }
export function useLocation(): string {
  return useSyncExternalStore(subscribe, () => window.location.pathname + window.location.search, () => "/");
}

let currentParams: Record<string, string> = {};
export function setParams(p: Record<string, string>) { currentParams = p; }
export function getParams() { return currentParams; }
