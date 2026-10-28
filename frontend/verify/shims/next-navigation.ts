// Verification stand-in for next/navigation (client hooks used by the pages).
import { useMemo } from "react";
import { getParams, navigate, useLocation } from "./router-core";

export function usePathname(): string { return useLocation().split("?")[0] ?? "/"; }
export function useSearchParams(): URLSearchParams {
  const loc = useLocation();
  return useMemo(() => new URLSearchParams(loc.includes("?") ? loc.slice(loc.indexOf("?")) : ""), [loc]);
}
export function useParams<T extends Record<string, string> = Record<string, string>>(): T { useLocation(); return getParams() as T; }
export function useRouter() {
  return { push: (h: string) => navigate(h), replace: (h: string) => navigate(h, true), back: () => window.history.back(),
           refresh: () => window.location.reload(), prefetch: () => undefined };
}
export function notFound(): never { throw new Error("NEXT_NOT_FOUND"); }
