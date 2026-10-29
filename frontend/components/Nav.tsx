"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Building2, Gauge, LayoutDashboard, Search, Settings, Target, Users } from "lucide-react";
import { type ComponentType } from "react";
import { BrandLockup } from "./Brand";

type Item = { href: string; label: string; short: string; icon: ComponentType<{ size?: number; "aria-hidden"?: boolean }>;
              also: string[] };

/**
 * Primary sections (refocus of 28 Oct 2026): discover an opportunity, understand it, research the people,
 * find relationships or introduction routes, track progress. The Control panel (29 Oct 2026) adds opportunities per market and the
 * score out of 100. Organisation profiles open from opportunities and people.
 * Source management, evidence review, scanning controls and the optional WFC-data tools live under Settings; their pages
 * are kept and highlight Settings when open.
 */
export const NAV: Item[] = [
  { href: "/", label: "Overview", short: "Overview", icon: LayoutDashboard, also: [] },
  { href: "/control-panel", label: "Control panel", short: "Panel", icon: Gauge, also: [] },
  { href: "/opportunities", label: "Opportunities", short: "Opps", icon: Target, also: ["/records", "/signals"] },
  { href: "/discovery", label: "Discover", short: "Discover", icon: Search, also: [] },
  { href: "/companies", label: "Companies", short: "Companies", icon: Building2, also: ["/airlines-forwarders", "/organisations"] },
  { href: "/relationships", label: "Relationships", short: "People", icon: Users, also: [] },
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
