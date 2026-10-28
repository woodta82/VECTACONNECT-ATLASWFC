"use client";

import { useEffect, useState } from "react";
import { LogOut } from "lucide-react";
import { api, VERTICAL_LABELS, type ScannerStatus } from "@/lib/api";
import GlobalSearch from "./GlobalSearch";
import NotificationBell from "./NotificationBell";

function formatRelative(iso: string | null, future: boolean): string {
  if (!iso) return "—";
  const diffMs = future ? new Date(iso).getTime() - Date.now() : Date.now() - new Date(iso).getTime();
  if (future && diffMs <= 0) return "any moment";
  const mins = Math.round(Math.abs(diffMs) / 60000);
  if (mins < 60) return future ? `in ${mins}m` : `${mins}m ago`;
  const hours = Math.round(mins / 60);
  return future ? `in ${hours}h` : `${hours}h ago`;
}

export default function LiveStatusBar() {
  const [status, setStatus] = useState<ScannerStatus | null>(null);

  useEffect(() => {
    let active = true;
    const load = () => api.scannerStatus().then((s) => active && setStatus(s)).catch(() => {});
    load();
    const timer = setInterval(load, 15000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);

  return (
    <div
      className="flex items-center justify-between gap-4 px-5 md:px-8 py-2.5 text-xs border-b flex-wrap"
      style={{ borderColor: "var(--border)", background: "var(--panel)" }}
    >
      <div className="flex items-center gap-2">
        <span className="relative flex h-2 w-2">
          <span
            className={`absolute inline-flex h-full w-full rounded-full opacity-60 ${
              status?.enabled ? "bg-accent animate-ping" : "bg-gray-500"
            }`}
          />
          <span className={`relative inline-flex rounded-full h-2 w-2 ${status?.enabled ? "bg-accent" : "bg-gray-500"}`} />
        </span>
        <span className="text-muted">
          {status?.enabled ? "Global Scanner active" : "Global Scanner disabled"}
          {status?.last_vertical ? ` · last: ${VERTICAL_LABELS[status.last_vertical]}` : ""}
        </span>
        <span className="text-muted hidden sm:inline">
          · Last sweep {formatRelative(status?.last_cycle_completed_at ?? null, false)} · Next sweep{" "}
          {formatRelative(status?.next_cycle_at ?? null, true)}
        </span>
      </div>
      <div className="flex items-center gap-3">
        <GlobalSearch />
        <NotificationBell />
        <button
          onClick={() => api.logout()}
          aria-label="Log out"
          title="Log out"
          className="flex items-center justify-center h-8 w-8 rounded-lg hover:bg-[var(--panel-raised)]"
          style={{ color: "var(--text-muted)" }}
        >
          <LogOut size={16} />
        </button>
      </div>
    </div>
  );
}
