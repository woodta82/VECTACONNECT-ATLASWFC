"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Target, Globe2, Users, BarChart3 } from "lucide-react";

const NAV = [
  { href: "/", label: "Panel", icon: LayoutDashboard },
  { href: "/opportunities", label: "Pipeline", icon: Target },
  { href: "/regional", label: "Regional", icon: Globe2 },
  { href: "/relationships", label: "Contacts", icon: Users },
  { href: "/reports", label: "Reports", icon: BarChart3 },
];

export default function MobileNav() {
  const pathname = usePathname();

  return (
    <nav
      className="md:hidden fixed bottom-0 left-0 right-0 z-50 flex items-center justify-around border-t py-2"
      style={{ borderColor: "var(--border)", background: "var(--panel)" }}
      aria-label="Primary"
    >
      {NAV.map(({ href, label, icon: Icon }) => {
        const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className="flex flex-col items-center gap-0.5 px-2 py-1 text-[10px] font-medium"
            style={{ color: active ? "var(--accent-text)" : "var(--text-muted)" }}
          >
            <Icon size={20} aria-hidden="true" />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
