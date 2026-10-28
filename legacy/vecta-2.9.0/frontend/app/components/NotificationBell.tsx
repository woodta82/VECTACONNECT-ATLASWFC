"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Bell } from "lucide-react";
import { api, type Notification } from "@/lib/api";

export default function NotificationBell() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [notifications, setNotifications] = useState<Notification[]>([]);

  useEffect(() => {
    let active = true;
    const load = () => api.unreadNotificationCount().then((r) => active && setUnreadCount(r.count)).catch(() => {});
    load();
    const timer = setInterval(load, 20000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);

  function toggle() {
    const next = !open;
    setOpen(next);
    if (next) api.notifications().then(setNotifications).catch(() => {});
  }

  async function handleClick(n: Notification) {
    if (!n.read) {
      await api.markNotificationRead(n.id);
      setUnreadCount((c) => Math.max(0, c - 1));
      setNotifications((prev) => prev.map((x) => (x.id === n.id ? { ...x, read: true } : x)));
    }
    if (n.opportunity_id) {
      setOpen(false);
      router.push(`/opportunities/${n.opportunity_id}`);
    } else if (n.contact_id) {
      setOpen(false);
      router.push(`/relationships/${n.contact_id}`);
    }
  }

  return (
    <div className="relative">
      <button
        onClick={toggle}
        aria-label={unreadCount > 0 ? `Notifications, ${unreadCount} unread` : "Notifications"}
        aria-expanded={open}
        aria-haspopup="true"
        className="relative flex items-center justify-center rounded-lg border p-2"
        style={{ borderColor: "var(--border-strong)" }}
      >
        <Bell size={16} className="text-muted" aria-hidden="true" />
        {unreadCount > 0 && (
          <span
            className="absolute -top-1.5 -right-1.5 flex h-4 min-w-[16px] items-center justify-center rounded-full px-1 text-[10px] font-semibold text-white"
            style={{ background: "var(--danger)" }}
            aria-hidden="true"
          >
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div
            className="absolute right-0 top-full mt-2 w-80 max-h-96 overflow-y-auto rounded-xl z-50"
            style={{ background: "var(--panel)", border: "1px solid var(--border-strong)" }}
            role="menu"
            aria-label="Notifications"
          >
            <p className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-muted border-b" style={{ borderColor: "var(--border)" }}>
              Notifications
            </p>
            {notifications.length === 0 && <p className="px-4 py-6 text-sm text-muted text-center">No notifications yet.</p>}
            {notifications.map((n) => (
              <button
                key={n.id}
                role="menuitem"
                onClick={() => handleClick(n)}
                className="w-full text-left px-4 py-3 border-b last:border-0 transition-colors"
                style={{ borderColor: "var(--border)", opacity: n.read ? 0.55 : 1 }}
                onMouseEnter={(e) => (e.currentTarget.style.background = "var(--panel-raised)")}
                onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
              >
                <p className="text-sm text-main font-medium">{n.title}</p>
                <p className="text-xs text-muted mt-0.5 line-clamp-2">{n.body}</p>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
