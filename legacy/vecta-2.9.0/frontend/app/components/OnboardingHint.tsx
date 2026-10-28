"use client";

import { useEffect, useState } from "react";
import { X } from "lucide-react";

export default function OnboardingHint({ id, children }: { id: string; children: React.ReactNode }) {
  const storageKey = `atlas-hint-dismissed-${id}`;
  const [dismissed, setDismissed] = useState(true); // default hidden until we check localStorage, avoids flash

  useEffect(() => {
    try {
      setDismissed(localStorage.getItem(storageKey) === "1");
    } catch {
      // localStorage unavailable — just show the hint every time, harmless
      setDismissed(false);
    }
  }, [storageKey]);

  function dismiss() {
    setDismissed(true);
    try {
      localStorage.setItem(storageKey, "1");
    } catch {
      // ignore — nothing to persist to, hint will just reappear next visit
    }
  }

  if (dismissed) return null;

  return (
    <div
      className="flex items-start gap-3 px-4 py-3 rounded-xl mb-5 text-sm"
      style={{ background: "var(--accent-wash)", border: "1px solid var(--accent)" }}
      role="note"
    >
      <div className="flex-1" style={{ color: "var(--accent-text)" }}>
        {children}
      </div>
      <button onClick={dismiss} aria-label="Dismiss hint" className="shrink-0" style={{ color: "var(--accent-text)" }}>
        <X size={16} />
      </button>
    </div>
  );
}
