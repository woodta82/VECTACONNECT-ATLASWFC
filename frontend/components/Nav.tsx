"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3, Building2, Cable, ChevronRight, ClipboardCheck, Database, Gauge, LayoutGrid, LayoutDashboard, MoreHorizontal, Network, Plane, Route, Search,
  Settings, ShieldCheck, Target, Users,
} from "lucide-react";
import { type ComponentType, useEffect, useState } from "react";
import { BrandLockup } from "./Brand";

type Item = { href: string; label: string; short: string; icon: ComponentType<{ size?: number; "aria-hidden"?: boolean }> };
type Group = { id: string; label: string; items: Item[] };

/**
 * Progressive disclosure (review of 26 Oct 2026, §2 "navigation"): the everyday path is four items:
 * Briefing, Discover, Opportunities, Accounts. Every other capability stays one click away in a named group,
 * and a group opens by itself when the current page is inside it. Nothing was removed.
 */
export const PRIMARY: Item[] = [
  { href: "/", label: "Briefing", short: "Briefing", icon: LayoutDashboard },
  { href: "/discovery", label: "Discover", short: "Discover", icon: Search },
  { href: "/opportunities", label: "Opportunities", short: "Opps", icon: Target },
  { href: "/airlines-forwarders", label: "Accounts", short: "Accounts", icon: Plane },
];

export const GROUPS: Group[] = [
  { id: "specialist", label: "Specialist areas", items: [
    { href: "/areas", label: "Capability Areas", short: "Areas", icon: LayoutGrid },
    { href: "/lanes", label: "Trade Lanes and Capacity", short: "Lanes", icon: Route },
    { href: "/service", label: "Service Intelligence", short: "Service", icon: Gauge },
    { href: "/capabilities", label: "Group Capabilities", short: "Capability", icon: ShieldCheck },
    { href: "/relationships", label: "Relationships", short: "People", icon: Users },
    { href: "/network", label: "Network Development", short: "Network", icon: Network },
    { href: "/reports", label: "Reports", short: "Reports", icon: BarChart3 },
  ] },
  { id: "evidence", label: "Evidence and data", items: [
    { href: "/review", label: "Evidence Review", short: "Review", icon: ClipboardCheck },
    { href: "/sources", label: "Public Sources", short: "Sources", icon: Database },
    { href: "/data-sources", label: "Data Sources and Imports", short: "Data", icon: Cable },
  ] },
  { id: "admin", label: "Administration", items: [
    { href: "/settings", label: "Settings", short: "Settings", icon: Settings },
  ] },
];

/** Every destination, in order (used by tests and the command surfaces). */
export const NAV: Item[] = [...PRIMARY, ...GROUPS.flatMap((g) => g.items)];

function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}

function NavLink({ item, pathname }: { item: Item; pathname: string }) {
  const Icon = item.icon;
  return (
    <Link href={item.href} aria-current={isActive(pathname, item.href) ? "page" : undefined}>
      <Icon size={17} aria-hidden />
      {item.label}
    </Link>
  );
}

function NavGroup({ group, pathname }: { group: Group; pathname: string }) {
  const containsActive = group.items.some((i) => isActive(pathname, i.href));
  const [open, setOpen] = useState(containsActive);
  useEffect(() => { if (containsActive) setOpen(true); }, [containsActive]);
  return (
    <div className="nav-section">
      <button type="button" className="nav-group-toggle" aria-expanded={open} aria-controls={`nav-${group.id}`} onClick={() => setOpen(!open)}>
        <ChevronRight size={14} aria-hidden className="chev" />
        {group.label}
      </button>
      <div id={`nav-${group.id}`} className="nav-group-items" hidden={!open}>
        {group.items.map((i) => <NavLink key={i.href} item={i} pathname={pathname} />)}
      </div>
    </div>
  );
}

export function Sidebar({ customer }: { customer: string }) {
  const pathname = usePathname() ?? "/";
  return (
    <aside className="sidebar" aria-label="Primary">
      <BrandLockup href="/" />
      <nav className="nav" aria-label="Sections">
        {PRIMARY.map((i) => <NavLink key={i.href} item={i} pathname={pathname} />)}
        {GROUPS.map((g) => <NavGroup key={g.id} group={g} pathname={pathname} />)}
      </nav>
      <div className="sidebar-foot">
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <Building2 size={13} aria-hidden /> Configured for {customer}
        </div>
        <div style={{ marginTop: 4 }}>Shared login · all loaded records visible</div>
      </div>
    </aside>
  );
}

export function MobileNav() {
  const pathname = usePathname() ?? "/";
  const [more, setMore] = useState(false);
  const inMore = GROUPS.some((g) => g.items.some((i) => isActive(pathname, i.href)));
  useEffect(() => { setMore(false); }, [pathname]);
  return (
    <>
      {more && (
        <div className="mobile-more" id="mobile-more" role="dialog" aria-label="More sections">
          {GROUPS.map((g) => (
            <div key={g.id}>
              <div className="nav-group">{g.label}</div>
              <div className="mobile-more-grid">
                {g.items.map((i) => {
                  const Icon = i.icon;
                  return (
                    <Link key={i.href} href={i.href} aria-current={isActive(pathname, i.href) ? "page" : undefined}>
                      <Icon size={18} aria-hidden />{i.label}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
      <nav className="mobile-nav" aria-label="Sections (mobile)">
        {PRIMARY.map(({ href, short, label, icon: Icon }) => (
          <Link key={href} href={href} aria-label={label} aria-current={isActive(pathname, href) ? "page" : undefined}>
            <Icon size={18} aria-hidden />
            {short}
          </Link>
        ))}
        <button type="button" className={inMore ? "is-current" : undefined} aria-expanded={more} aria-controls="mobile-more"
                onClick={() => setMore(!more)}>
          <MoreHorizontal size={18} aria-hidden />
          More
        </button>
      </nav>
    </>
  );
}
