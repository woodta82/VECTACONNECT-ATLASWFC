"use client";

import { useCallback, useState } from "react";
import { ApiError } from "./api";

export type ActionState = { busy: boolean; error: string | null; ok: string | null };

/** Runs a mutation with visible busy / error / success state. Failures are
 * always shown (never swallowed), with the server's reason and request id. */
export function useAction() {
  const [state, setState] = useState<ActionState>({ busy: false, error: null, ok: null });
  const run = useCallback(async <T,>(fn: () => Promise<T>, ok?: string | ((r: T) => string)): Promise<T | undefined> => {
    setState({ busy: true, error: null, ok: null });
    try {
      const r = await fn();
      setState({ busy: false, error: null, ok: typeof ok === "function" ? ok(r) : ok ?? null });
      return r;
    } catch (e) {
      const msg = e instanceof ApiError ? `${e.message}${e.requestId ? ` (reference ${e.requestId})` : ""}` : "The action failed. Try again.";
      setState({ busy: false, error: msg, ok: null });
      return undefined;
    }
  }, []);
  const clear = useCallback(() => setState({ busy: false, error: null, ok: null }), []);
  return { ...state, run, clear };
}
