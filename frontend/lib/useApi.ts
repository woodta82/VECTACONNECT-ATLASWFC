"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "./api";

export type LoadState<T> =
  | { status: "loading"; data: null; error: null }
  | { status: "ready"; data: T; error: null }
  | { status: "error"; data: T | null; error: ApiError };

/** Fetch on mount and whenever `path` changes. A failed refresh keeps the
 * previous data visible but flags it as stale rather than blanking it. */
export function useApi<T>(path: string | null): LoadState<T> & { reload: () => void; stale: boolean } {
  const [state, setState] = useState<LoadState<T>>({ status: "loading", data: null, error: null });
  const [tick, setTick] = useState(0);
  const last = useRef<T | null>(null);

  useEffect(() => {
    if (path === null) return;
    let cancelled = false;
    setState((s) => (s.data !== null ? s : { status: "loading", data: null, error: null }));
    api
      .get<T>(path)
      .then((data) => {
        if (cancelled) return;
        last.current = data;
        setState({ status: "ready", data, error: null });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const e = err instanceof ApiError ? err : new ApiError(0, "unknown", "Unexpected error", null);
        setState({ status: "error", data: last.current, error: e });
      });
    return () => {
      cancelled = true;
    };
  }, [path, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { ...state, reload, stale: state.status === "error" && state.data !== null };
}
