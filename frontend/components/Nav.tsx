"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Building2, LayoutDashboard, Search, Settings, Target, Users } from "lucide-react";
import { type ComponentType } from "react";
import { BrandLockup } from "./Brand";

type Item = { href: string; label: string; short: string; icon: ComponentType<{ size?: number; "aria-hidden"?: boolean }>;
              also: string[] };

/**
 * One workspace (30 Oct 2026): Dashboard (the Overview and the Control panel consolidated), Discover (the research process and its
 * progress), Opportunities (saved commercial opportunities and linked market signals), Relationships (Companies and People as two
 * connected views), Settings (technical controls and optional data tools). Old addresses keep working and highlight their section.
 */
export const NAV: Item[] = [
  { href: "/", label: "Dashboard", short: "Dashboard", icon: LayoutDashboard, also: ["/control-panel"] },
  { href: "/discovery", label: "Discover", short: "Discover", icon: Search, also: [] },
  { href: "/opportunities", label: "Opportunities", short: "Opps", icon: Target, also: ["/records", "/signals"] },
  { href: "/relationships", label: "Relationships", short: "People", icon: Users, also: ["/companies", "/airlines-forwarders", "/organisations", "/people"] },
  { href: "/settings", label: "Settings", short: "Settings", icon: Settings,
    also: ["/sources", "/review", "/data-sources", "/areas", "/lanes", "/service", "/capabilities", "/network", "/reports"] },
];

function matches(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}

export function isActive(pathname: string, item: Item): boolean {
  return matches(pathname, item.href) || item.also.some((a) => matches(pathname, a));
}

export function Sidebar({ customer }: { customer: string }) {
  const pathname = usePathname() ?? "/";
  return (
    <aside className="sidebar" aria-label="Primary">
      <BrandLockup href="/" />
      <nav className="nav" aria-label="Sections">
        {NAV.map((item) => {
          const Icon = item.icon;
          return (
            <Link key={item.href} href={item.href} aria-current={isActive(pathname, item) ? "page" : undefined}>
              <Icon size={17} aria-hidden />
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="sidebar-foot">
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <Building2 size={13} aria-hidden /> Configured for {customer}
        </div>
        <div style={{ marginTop: 4 }}>Shared workspace · one login</div>
      </div>
    </aside>
  );
}

export function MobileNav() {
  const pathname = usePathname() ?? "/";
  return (
    <nav className="mobile-nav" aria-label="Sections (mobile)">
      {NAV.map((item) => {
        const Icon = item.icon;
        return (
          <Link key={item.href} href={item.href} aria-label={item.label} aria-current={isActive(pathname, item) ? "page" : undefined}>
            <Icon size={18} aria-hidden />
            {item.short}
          </Link>
        );
      })}
    </nav>
  );
}
