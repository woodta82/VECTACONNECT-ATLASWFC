import Image from "next/image";
import Link from "next/link";

/** The exact three-line product hierarchy. Do not change spelling or case. */
export const BRAND_LINES = ["VECTA Connect", "ATLAS", "DYNAMIC MARKET INTELLIGENCE"] as const;
export const BRAND_METADATA = "VECTA Connect | ATLAS | DYNAMIC MARKET INTELLIGENCE";

export function BrandLockup({ size = "md", href }: { size?: "md" | "lg"; href?: string }) {
  const body = (
    <>
      {/* Decorative: the lockup's accessible name is on the wrapper. `unoptimized`: a 50 KB mark needs no resizing pipeline. */}
      <Image src="/vecta-mark.png" alt="" aria-hidden="true" className="brand-mark" width={44} height={11} priority unoptimized />
      <span className="brand-lines">
        <span className="brand-l1">{BRAND_LINES[0]}</span>
        <span className="brand-l2">{BRAND_LINES[1]}</span>
        <span className="brand-l3">{BRAND_LINES[2]}</span>
      </span>
    </>
  );
  const cls = `brand ${size === "lg" ? "brand-lg" : ""}`;
  return href ? (
    <Link href={href} className={cls} aria-label={BRAND_METADATA}>
      {body}
    </Link>
  ) : (
    <div className={cls} role="img" aria-label={BRAND_METADATA}>
      {body}
    </div>
  );
}
