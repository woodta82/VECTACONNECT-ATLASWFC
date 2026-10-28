"use client";

import { useEffect, useState } from "react";
import { api, type AdminSettings, type ScanHealth } from "@/lib/api";
import PageHeader from "../components/PageHeader";

export default function SettingsPage() {
  const [adminSettings, setAdminSettings] = useState<AdminSettings | null>(null);
  const [health, setHealth] = useState<ScanHealth | null>(null);
  const [isLight, setIsLight] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pwCurrent, setPwCurrent] = useState("");
  const [pwNew, setPwNew] = useState("");
  const [pwConfirm, setPwConfirm] = useState("");
  const [pwBusy, setPwBusy] = useState(false);
  const [pwMessage, setPwMessage] = useState<{ ok: boolean; text: string } | null>(null);

  function load() {
    setError(null);
    Promise.all([api.adminSettings(), api.scanHealth()])
      .then(([s, h]) => {
        setAdminSettings(s);
        setHealth(h);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load settings"));
    setIsLight(document.documentElement.classList.contains("light"));
  }

  useEffect(() => {
    load();
  }, []);

  function toggleTheme() {
    const next = !isLight;
    setIsLight(next);
    document.documentElement.classList.toggle("light", next);
    try {
      localStorage.setItem("atlas-theme", next ? "light" : "dark");
    } catch {
      // localStorage unavailable — theme just won't persist across reloads
    }
  }

  async function updateInterval(hours: number) {
    try {
      const updated = await api.updateAdminSettings({ scan_interval_hours: hours });
      setAdminSettings(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update sweep interval");
    }
  }

  async function toggleScanning() {
    if (!adminSettings) return;
    try {
      const updated = await api.updateAdminSettings({ scan_enabled: !adminSettings.scan_enabled });
      setAdminSettings(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update scanning status");
    }
  }

  async function toggleNotifyPref(
    key: "notify_priority_enabled" | "notify_deadline_enabled" | "notify_new_contact_enabled"
  ) {
    if (!adminSettings) return;
    try {
      const updated = await api.updateAdminSettings({ [key]: !adminSettings[key] });
      setAdminSettings(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update notification preference");
    }
  }

  async function submitPasswordChange() {
    setPwMessage(null);
    if (pwNew !== pwConfirm) {
      setPwMessage({ ok: false, text: "New password and confirmation don't match." });
      return;
    }
    setPwBusy(true);
    try {
      const result = await api.changePassword(pwCurrent, pwNew);
      setPwCurrent("");
      setPwNew("");
      setPwConfirm("");
      setPwMessage({ ok: true, text: result.detail });
      // The backend revokes every session on success — the next API call
      // will 401 and AuthGate will show the login screen automatically.
    } catch (e) {
      setPwMessage({ ok: false, text: e instanceof Error ? e.message : "Password change failed" });
    } finally {
      setPwBusy(false);
    }
  }

  return (
    <div>
      <PageHeader eyebrow="Settings & Admin" title="Configuration" />

      {error && (
        <div className="panel p-5 mb-5" style={{ borderColor: "var(--danger)" }} role="alert">
          <p className="text-sm font-semibold mb-1" style={{ color: "var(--danger)" }}>
            Couldn&apos;t load settings
          </p>
          <p className="text-sm text-muted mb-3">{error}</p>
          <button onClick={load} className="btn btn-secondary text-xs">
            Try again
          </button>
        </div>
      )}

      {!adminSettings && !error && <p className="text-sm text-muted mb-5">Loading…</p>}

      {adminSettings && !adminSettings.anthropic_key_configured && (
        <div className="panel p-5 mb-5" style={{ borderColor: "var(--danger)" }} role="alert">
          <h2 className="text-sm font-semibold mb-2" style={{ color: "var(--danger)" }}>
            Action needed
          </h2>
          <ul className="text-sm text-muted space-y-1 list-disc list-inside">
            <li>
              <span className="text-main">ANTHROPIC_API_KEY is not set</span> — this is why the Global
              Scanner shows as disabled/empty: every scan call will fail without it. Set it on the
              backend service and redeploy.
            </li>
          </ul>
        </div>
      )}

      <div className="panel p-5 mb-5">
        <h2 className="text-sm font-semibold text-main mb-1">Change password</h2>
        <p className="text-xs text-muted mb-4">
          Minimum 12 characters with at least three of: lowercase, uppercase, digits, symbols.
          Changing the password logs out every active session, including this one.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-3">
          <div className="field">
            <label htmlFor="pw-current" className="field-label">Current password</label>
            <input
              id="pw-current"
              type="password"
              autoComplete="current-password"
              value={pwCurrent}
              onChange={(e) => setPwCurrent(e.target.value)}
              className="input"
            />
          </div>
          <div className="field">
            <label htmlFor="pw-new" className="field-label">New password</label>
            <input
              id="pw-new"
              type="password"
              autoComplete="new-password"
              value={pwNew}
              onChange={(e) => setPwNew(e.target.value)}
              className="input"
            />
          </div>
          <div className="field">
            <label htmlFor="pw-confirm" className="field-label">Confirm new password</label>
            <input
              id="pw-confirm"
              type="password"
              autoComplete="new-password"
              value={pwConfirm}
              onChange={(e) => setPwConfirm(e.target.value)}
              className="input"
            />
          </div>
        </div>
        {pwMessage && (
          <p className="text-xs mb-3" style={{ color: pwMessage.ok ? "var(--accent-text)" : "var(--danger)" }}>
            {pwMessage.text}
          </p>
        )}
        <button
          onClick={submitPasswordChange}
          disabled={pwBusy || !pwCurrent || !pwNew || !pwConfirm}
          className="btn btn-primary"
        >
          {pwBusy ? "Changing…" : "Change password"}
        </button>
      </div>

      <div className="panel p-5 mb-5">
        <h2 className="text-sm font-semibold text-main mb-3">Configuration status</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-sm">
          <StatusRow label="Anthropic API key" ok={adminSettings?.anthropic_key_configured} />
          <StatusRow label="Login gate" ok={true} />
          <StatusRow label="Email digest (Resend)" ok={adminSettings?.resend_key_configured} optional />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 mb-5">
        <div className="panel p-5">
          <h2 className="text-sm font-semibold text-main mb-1">Global Scanner schedule</h2>
          <p className="text-xs text-muted mb-3">
            Off by default — nothing runs automatically or costs anything until you turn this on or
            manually click &quot;Run Global Scan&quot; / submit a Regional Search. Saved searches can
            never trigger a scan on a schedule any more, by design — see docs/SECURITY.md.
          </p>
          {adminSettings && (
            <div className="space-y-4">
              <div className="flex items-center justify-between text-sm">
                <span className="text-main">Automation engine</span>
                <button
                  onClick={toggleScanning}
                  role="switch"
                  aria-checked={adminSettings.scan_enabled}
                  className="badge"
                  style={{
                    background: adminSettings.scan_enabled ? "var(--accent)" : "var(--panel-raised)",
                    color: adminSettings.scan_enabled ? "#fff" : "var(--text-muted)",
                  }}
                >
                  {adminSettings.scan_enabled ? "Enabled" : "Disabled"}
                </button>
              </div>
              <div className="field">
                <label htmlFor="sweep-interval" className="field-label">Sweep interval (hours)</label>
                <input
                  id="sweep-interval"
                  type="number"
                  min={1}
                  step={1}
                  defaultValue={adminSettings.scan_interval_hours}
                  onBlur={(e) => updateInterval(Number(e.target.value))}
                  className="input w-32"
                />
                <p className="text-xs text-muted">
                  Only applies while Automation engine (above) is enabled. Changes apply immediately but
                  are not persisted across a restart — update SCAN_INTERVAL_HOURS in the environment for
                  a permanent change.
                </p>
              </div>
              <p className="text-xs text-muted">Daily digest composed at {adminSettings.digest_hour_local}:00 (server time).</p>
            </div>
          )}
        </div>

        <div className="panel p-5">
          <h2 className="text-sm font-semibold text-main mb-3">Appearance</h2>
          <div className="flex items-center justify-between text-sm">
            <span className="text-main">Theme</span>
            <button onClick={toggleTheme} className="btn btn-secondary text-xs" aria-pressed={isLight}>
              {isLight ? "Light mode" : "Dark mode"} — switch
            </button>
          </div>
          <p className="text-xs text-muted mt-2">Dark navy is the default, matching VECTA Sports branding.</p>
        </div>
      </div>

      <div className="panel p-5 mb-5">
        <h2 className="text-sm font-semibold text-main mb-1">Notification preferences</h2>
        <p className="text-xs text-muted mb-4">
          Global for now — there&apos;s no per-user login yet (see docs/SECURITY.md), so these apply to the
          whole in-app notification feed and digest, not per person.
        </p>
        {adminSettings && (
          <div className="space-y-3">
            <NotifyToggle
              label="Priority opportunities"
              checked={adminSettings.notify_priority_enabled}
              onToggle={() => toggleNotifyPref("notify_priority_enabled")}
            />
            <NotifyToggle
              label="Deadline alerts (T-14/T-7/T-2)"
              checked={adminSettings.notify_deadline_enabled}
              onToggle={() => toggleNotifyPref("notify_deadline_enabled")}
            />
            <NotifyToggle
              label="New contacts discovered"
              checked={adminSettings.notify_new_contact_enabled}
              onToggle={() => toggleNotifyPref("notify_new_contact_enabled")}
            />
          </div>
        )}
      </div>

      <div className="panel p-5 mb-5">
        <h2 className="text-sm font-semibold text-main mb-3">Scan health</h2>
        {health ? (
          <div className="grid grid-cols-3 gap-4 text-sm mb-4">
            <div>
              <p className="field-label">Recent scans</p>
              <p className="text-main text-xl font-semibold font-display mt-0.5">{health.recent_scans}</p>
            </div>
            <div>
              <p className="field-label">Failed</p>
              <p className="text-main text-xl font-semibold font-display mt-0.5">{health.failed_scans}</p>
            </div>
            <div>
              <p className="field-label">Success rate</p>
              <p className="text-main text-xl font-semibold font-display mt-0.5">
                {health.success_rate != null ? `${Math.round(health.success_rate * 100)}%` : "—"}
              </p>
            </div>
          </div>
        ) : (
          <p className="text-sm text-muted">Loading…</p>
        )}
        {health && health.recent_failures.length > 0 && (
          <div className="space-y-1.5 pt-3 border-t" style={{ borderColor: "var(--border)" }}>
            {health.recent_failures.map((f) => (
              <div key={f.id} className="text-xs text-muted">
                {f.type} · {f.vertical_scope ?? "—"} · {f.error}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function StatusRow({ label, ok, optional = false }: { label: string; ok?: boolean; optional?: boolean }) {
  const color = ok ? "var(--success)" : optional ? "var(--text-muted)" : "var(--danger)";
  return (
    <div className="flex items-center gap-2">
      <span className="h-2 w-2 rounded-full shrink-0" style={{ background: color }} aria-hidden="true" />
      <span className="text-main">{label}</span>
      <span className="ml-auto text-xs" style={{ color }}>
        {ok ? "Set" : optional ? "Not set (optional)" : "Not set"}
      </span>
    </div>
  );
}

function NotifyToggle({ label, checked, onToggle }: { label: string; checked: boolean; onToggle: () => void }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-main">{label}</span>
      <button
        onClick={onToggle}
        role="switch"
        aria-checked={checked}
        aria-label={label}
        className="badge"
        style={{
          background: checked ? "var(--accent)" : "var(--panel-raised)",
          color: checked ? "#fff" : "var(--text-muted)",
        }}
      >
        {checked ? "On" : "Off"}
      </button>
    </div>
  );
}
