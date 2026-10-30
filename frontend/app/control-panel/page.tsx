"use client";

/* The Control panel (29 Oct 2026) is part of the Dashboard since 30 Oct 2026. The old address is kept: it opens the Dashboard, whose
   expandable detail holds the score distributions and breakdowns. */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

export default function ControlPanelRedirect() {
  const router = useRouter();
  useEffect(() => { router.replace("/"); }, [router]);
  return <p className="muted small">The Control panel is now part of the <Link href="/">Dashboard</Link> (score distributions and breakdowns under its detail).</p>;
}
