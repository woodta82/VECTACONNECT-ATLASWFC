"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { LogOut } from "lucide-react";
import { ApiError, api, registerUnauthenticatedHandler, setCsrf } from "@/lib/api";
import { setReportingTz } from "@/lib/format";
import { BRAND_METADATA, BrandLockup } from "./Brand";
import { MobileNav, Sidebar } from "./Nav";

type SessionInfo = { customer: string; release: string; reporting_timezone: string; active_sessions: number };
const SessionCtx = createContext<SessionInfo | null>(null);
export const useSession = () => useContext(SessionCtx);

type Phase = "checking" | "signed_out" | "signed_in";

/** Removes the VECTA 2.9 app-shell service worker and its caches. */
function useRetireLegacyServiceWorker() {
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
    navigator.serviceWorker.getRegistrations().then((regs) => regs.forEach((r) => r.unregister())).catch(() => undefined);
    if ("caches" in window) {
      caches.keys().then((keys) => keys.filter((k) => k.startsWith("atlas")).forEach((k) => caches.delete(k))).catch(() => undefined);
    }
  }, []);
}

export default function AuthShell({ children }: { children: ReactNode }) {
  const [phase, setPhase] = useState<Phase>("checking");
  const [info, setInfo] = useState<SessionInfo | null>(null);
  useRetireLegacyServiceWorker();

  const loadSession = useCallback(async () => {
    try {
      const s = await api.get<SessionInfo & { csrf_token: string }>("/auth/session");
      setCsrf(s.csrf_token);
      setReportingTz(s.reporting_timezone);
      setInfo(s);
      setPhase("signed_in");
    } catch {
      setPhase("signed_out");
    }
  }, []);

  useEffect(() => {
    registerUnauthenticatedHandler(() => {
      setInfo(null);
      setPhase("signed_out");
    });
    void loadSession();
    return () => registerUnauthenticatedHandler(null);
  }, [loadSession]);

  if (phase === "checking") {
    return (
      <div className="loading-screen" role="status" aria-live="polite">
        <BrandLockup size="lg" />
        <span className="sr-only">Loading {BRAND_METADATA}</span>
      </div>
    );
  }
  if (phase === "signed_out" || info === null) {
    return <LoginScreen onSuccess={loadSession} />;
  }

  return (
    <SessionCtx.Provider value={info}>
      <a href="#main-content" className="skip-link">Skip to main content</a>
      <div className="shell">
        <Sidebar customer={info.customer} />
        <div className="content">
          <StatusBar info={info} onSignedOut={() => setPhase("signed_out")} />
          <main id="main-content" tabIndex={-1}>{children}</main>
          <footer className="foot">
            <span>{BRAND_METADATA} · release {info.release}</span>
            <span>Configured for {info.customer}. Times shown in {info.reporting_timezone} unless stated.</span>
          </footer>
        </div>
      </div>
      <MobileNav />
    </SessionCtx.Provider>
  );
}

function StatusBar({ info, onSignedOut }: { info: SessionInfo; onSignedOut: () => void }) {
  const [busy, setBusy] = useState(false);
  async function signOut() {
    setBusy(true);
    try {
      await api.logout();
    } finally {
      setBusy(false);
      onSignedOut();
    }
  }
  return (
    <div className="statusbar">
      <span className="mobile-brand"><BrandLockup href="/" /></span>
      <span>
        Shared login · {info.active_sessions} active session{info.active_sessions === 1 ? "" : "s"}
      </span>
      <span className="statusbar-right">
        <ThemeToggle />
        <button type="button" className="btn btn-ghost" onClick={signOut} disabled={busy}>
          <LogOut size={14} aria-hidden /> Sign out
        </button>
      </span>
    </div>
  );
}

function ThemeToggle() {
  const [light, setLight] = useState(false);
  useEffect(() => {
    let saved: string | null = null;
    try {
      saved = localStorage.getItem("atlas-theme");
    } catch {
      /* storage unavailable */
    }
    const isLight = saved === "light";
    setLight(isLight);
    document.documentElement.classList.toggle("light", isLight);
  }, []);
  function toggle() {
    const next = !light;
    setLight(next);
    document.documentElement.classList.toggle("light", next);
    try {
      localStorage.setItem("atlas-theme", next ? "light" : "dark");
    } catch {
      /* storage unavailable */
    }
  }
  return (
    <button type="button" className="btn btn-ghost" onClick={toggle} aria-pressed={light}>
      {light ? "Dark" : "Light"} mode
    </button>
  );
}

function LoginScreen({ onSuccess }: { onSuccess: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const userRef = useRef<HTMLInputElement>(null);
  useEffect(() => userRef.current?.focus(), []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!username.trim() || !password) return;
    setBusy(true);
    setError(null);
    try {
      await api.login(username.trim(), password);
      setPassword("");
      onSuccess();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Sign-in failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-bg" id="main-content">
      <div className="login-card">
        <h1 className="sr-only">Sign in to VECTA Connect ATLAS</h1>
        <BrandLockup size="lg" />
        <p className="login-sub">Sign in with the shared account for this instance.</p>
        <form onSubmit={submit} noValidate className="stack">
          <label className="field" htmlFor="login-user">
            Username
            <input id="login-user" ref={userRef} className="input" autoComplete="username" value={username}
                   onChange={(e) => setUsername(e.target.value)} required />
          </label>
          <label className="field" htmlFor="login-pass">
            Password
            <input id="login-pass" type="password" className="input" autoComplete="current-password" value={password}
                   onChange={(e) => setPassword(e.target.value)} required />
          </label>
          {error && <p role="alert" className="login-error">{error}</p>}
          <button type="submit" className="btn btn-primary" style={{ width: "100%", justifyContent: "center" }}
                  disabled={busy || !username.trim() || !password}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </main>
  );
}
