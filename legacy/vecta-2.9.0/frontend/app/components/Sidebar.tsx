"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Target, Globe2, Users, Building2, BarChart3, Settings } from "lucide-react";

const NAV = [
  { href: "/", label: "Briefing", icon: LayoutDashboard },
  { href: "/control-panel", label: "Control Panel", icon: LayoutDashboard },
  { href: "/opportunities", label: "Opportunities", icon: Target },
  { href: "/regional", label: "Regional Search", icon: Globe2 },
  { href: "/relationships", label: "Relationship Intelligence", icon: Users },
  { href: "/organisations", label: "Organisations", icon: Building2 },
  { href: "/reports", label: "Reports", icon: BarChart3 },
  { href: "/settings", label: "Settings & Admin", icon: Settings },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside
      className="w-64 shrink-0 border-r p-5 hidden md:flex md:flex-col"
      style={{ borderColor: "var(--border)", background: "var(--panel)" }}
      aria-label="Primary"
    >
      <Link href="/" className="flex flex-col items-center text-center gap-2 mb-8 px-1 py-1 rounded-lg">
        <Image src="/vecta-lockup.png" alt="VECTA Sports" width={132} height={65} priority className="logo-adaptive" />
        <div className="text-sm font-semibold text-main leading-snug font-display" style={{ marginTop: "5mm" }}>
          ATLAS by VECTA Sports
        </div>
      </Link>

      <nav className="flex flex-col gap-0.5" aria-label="Sections">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors"
              style={{
                background: active ? "var(--accent-wash)" : "transparent",
                color: active ? "var(--accent-text)" : "var(--text)",
              }}
            >
              <Icon size={17} strokeWidth={2} aria-hidden="true" />
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto pt-5 border-t text-[11px] text-muted leading-relaxed" style={{ borderColor: "var(--border)" }}>
        Internal use only
        <br />
        VECTA Sports Commercial Division
      </div>
    </aside>
  );
}
