"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

const ROUTES: Record<string, { path: string; label: string }> = {
  p: { path: "/", label: "Control Panel" },
  o: { path: "/opportunities", label: "Opportunities" },
  r: { path: "/regional", label: "Regional Search" },
  c: { path: "/relationships", label: "Relationship Intelligence" },
  g: { path: "/organisations", label: "Organisations" },
  e: { path: "/reports", label: "Reports" },
  s: { path: "/settings", label: "Settings & Admin" },
};

export default function KeyboardShortcuts() {
  const router = useRouter();
  const [awaitingSecondKey, setAwaitingSecondKey] = useState(false);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | null = null;

    function isTypingContext(target: EventTarget | null) {
      if (!(target instanceof HTMLElement)) return false;
      const tag = target.tagName.toLowerCase();
      return tag === "input" || tag === "textarea" || tag === "select" || target.isContentEditable;
    }

    function onKeyDown(e: KeyboardEvent) {
      if (e.metaKey || e.ctrlKey || e.altKey || isTypingContext(e.target)) return;

      if (awaitingSecondKey) {
        const route = ROUTES[e.key.toLowerCase()];
        setAwaitingSecondKey(false);
        if (timer) clearTimeout(timer);
        if (route) {
          e.preventDefault();
          router.push(route.path);
        }
        return;
      }

      if (e.key.toLowerCase() === "g") {
        setAwaitingSecondKey(true);
        timer = setTimeout(() => setAwaitingSecondKey(false), 1500);
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      if (timer) clearTimeout(timer);
    };
  }, [awaitingSecondKey, router]);

  if (!awaitingSecondKey) return null;

  return (
    <div
      className="fixed bottom-20 md:bottom-6 left-1/2 -translate-x-1/2 z-[200] px-4 py-2.5 rounded-xl text-xs"
      style={{ background: "var(--panel-raised)", border: "1px solid var(--border-strong)" }}
      role="status"
    >
      <span className="text-muted">Go to: </span>
      {Object.entries(ROUTES).map(([key, r], i) => (
        <span key={key} className="text-main">
          {i > 0 && <span className="text-muted"> · </span>}
          <kbd className="font-semibold" style={{ color: "var(--accent-text)" }}>
            {key}
          </kbd>{" "}
          {r.label}
        </span>
      ))}
    </div>
  );
}
