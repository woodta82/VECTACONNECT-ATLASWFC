/**
 * Same-origin API client. The session lives in an HttpOnly cookie the page
 * cannot read; the CSRF token is held in memory only and refreshed from
 * GET /api/auth/session after a reload.
 */

export class ApiError extends Error {
  status: number;
  code: string;
  requestId: string | null;
  constructor(status: number, code: string, message: string, requestId: string | null) {
    super(message);
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

let csrfToken: string | null = null;
let onUnauthenticated: (() => void) | null = null;

export function setCsrf(token: string | null): void {
  csrfToken = token;
}

export function registerUnauthenticatedHandler(fn: (() => void) | null): void {
  onUnauthenticated = fn;
}

type Json = Record<string, unknown> | unknown[] | string | number | boolean | null;

async function request<T>(method: string, path: string, body?: Json | FormData): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  let payload: BodyInit | undefined;
  if (body instanceof FormData) {
    payload = body;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  if (method !== "GET" && csrfToken) headers["X-CSRF-Token"] = csrfToken;
  let res: Response;
  try {
    res = await fetch(`/api${path}`, { method, headers, body: payload, credentials: "same-origin", cache: "no-store" });
  } catch {
    throw new ApiError(0, "network", "The server could not be reached. Check your connection and try again.", null);
  }
  const requestId = res.headers.get("x-request-id");
  if (!res.ok) {
    let code = "http_error";
    let detail = `Request failed (${res.status})`;
    try {
      const data = (await res.json()) as { error?: { code?: string; detail?: string }; detail?: unknown };
      if (data.error) {
        code = data.error.code ?? code;
        detail = data.error.detail ?? detail;
      } else if (typeof data.detail === "string") {
        detail = data.detail;
      }
    } catch {
      /* non-JSON error body */
    }
    if (res.status === 401 && path !== "/auth/login") onUnauthenticated?.();
    throw new ApiError(res.status, code, detail, requestId);
  }
  const type = res.headers.get("content-type") ?? "";
  if (type.includes("application/json")) return (await res.json()) as T;
  return (await res.text()) as unknown as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: Json | FormData) => request<T>("POST", path, body),
  put: <T>(path: string, body?: Json) => request<T>("PUT", path, body),
  del: <T>(path: string) => request<T>("DELETE", path),

  async login(username: string, password: string): Promise<void> {
    const r = await request<{ csrf_token: string }>("POST", "/auth/login", { username, password });
    setCsrf(r.csrf_token);
  },
  async restoreSession(): Promise<boolean> {
    try {
      const r = await request<{ csrf_token: string }>("GET", "/auth/session");
      setCsrf(r.csrf_token);
      return true;
    } catch {
      return false;
    }
  },
  async logout(): Promise<void> {
    try {
      await request("POST", "/auth/logout");
    } finally {
      setCsrf(null);
    }
  },
  async logoutAll(): Promise<void> {
    await request("POST", "/auth/logout-all");
    setCsrf(null);
  },
};

export function qs(params: Record<string, string | number | null | undefined>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== null && v !== undefined && v !== "") p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}
