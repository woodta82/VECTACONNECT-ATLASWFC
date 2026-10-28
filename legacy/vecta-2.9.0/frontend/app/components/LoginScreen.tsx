"use client";

import { useEffect, useRef, useState } from "react";
import Image from "next/image";
import { Eye, EyeOff, Lock, Mail } from "lucide-react";
import { api } from "@/lib/api";

const REMEMBERED_EMAIL_KEY = "atlas-remembered-email";

export default function LoginScreen({ onSuccess }: { onSuccess: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [forgotMessage, setForgotMessage] = useState(false);
  const emailInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    try {
      const remembered = localStorage.getItem(REMEMBERED_EMAIL_KEY);
      if (remembered) {
        setEmail(remembered);
        setRememberMe(true);
      }
    } catch {
      // localStorage unavailable — just start with an empty field
    }
    emailInputRef.current?.focus();
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim() || !password) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.login(email.trim(), password);
      try {
        if (rememberMe) localStorage.setItem(REMEMBERED_EMAIL_KEY, email.trim());
        else localStorage.removeItem(REMEMBERED_EMAIL_KEY);
      } catch {
        // localStorage unavailable — remember-me just won't persist, login still works
      }
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Incorrect username or password");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="login-backdrop">
      <div className="login-glow login-glow-1" aria-hidden="true" />
      <div className="login-glow login-glow-2" aria-hidden="true" />
      <div className="login-glow login-glow-3" aria-hidden="true" />

      <div className="login-card">
        <Image src="/vecta-lockup.png" alt="VECTA Sports" width={150} height={74} priority className="mx-auto mb-5" />
        <h1 className="login-title">ATLAS by VECTA Sports</h1>
        <p className="login-subtitle">Commercial Intelligence System</p>

        <form onSubmit={handleSubmit} className="mt-8 space-y-5" noValidate>
          <div className="login-field">
            <Mail size={18} className="login-field-icon" aria-hidden="true" />
            <label htmlFor="login-email" className="sr-only">Email ID</label>
            <input
              ref={emailInputRef}
              id="login-email"
              type="email"
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Email ID"
              className="login-input"
              required
            />
          </div>

          <div className="login-field">
            <Lock size={18} className="login-field-icon" aria-hidden="true" />
            <label htmlFor="login-password" className="sr-only">Password</label>
            <input
              id="login-password"
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              className="login-input"
              required
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? "Hide password" : "Show password"}
              className="login-field-toggle"
            >
              {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
            </button>
          </div>

          {error && (
            <p role="alert" className="text-sm text-center" style={{ color: "#FCA5A5" }}>
              {error}
            </p>
          )}

          <div className="flex items-center justify-between text-sm">
            <label className="flex items-center gap-2 cursor-pointer" style={{ color: "rgba(255,255,255,0.85)" }}>
              <input
                type="checkbox"
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
                className="h-4 w-4"
              />
              Remember me
            </label>
            <button
              type="button"
              onClick={() => setForgotMessage(true)}
              className="italic hover:underline"
              style={{ color: "rgba(255,255,255,0.85)" }}
            >
              Forgot Password?
            </button>
          </div>

          {forgotMessage && (
            <p className="text-xs text-center" style={{ color: "rgba(255,255,255,0.7)" }}>
              Contact your VECTA Sports administrator to reset access.
            </p>
          )}

          <button type="submit" disabled={submitting || !email.trim() || !password} className="login-submit">
            {submitting ? "Signing in…" : "LOGIN"}
          </button>
        </form>
      </div>
    </div>
  );
}
