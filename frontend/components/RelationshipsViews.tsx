"use client";

/* Relationships = Companies and People, two connected views of the same saved results (30 Oct 2026). */

import Link from "next/link";

export function RelationshipsViews({ current }: { current: "people" | "companies" }) {
  return (
    <div className="segmented" role="group" aria-label="Relationships view" style={{ marginBottom: 12 }}>
      <Link href="/companies" aria-current={current === "companies" ? "page" : undefined} className={current === "companies" ? "is-active" : undefined}>Companies</Link>
      <Link href="/relationships" aria-current={current === "people" ? "page" : undefined} className={current === "people" ? "is-active" : undefined}>People</Link>
    </div>
  );
}
