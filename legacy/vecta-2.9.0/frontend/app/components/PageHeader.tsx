import Link from "next/link";

type Crumb = { label: string; href?: string };

export default function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  back,
}: {
  eyebrow: string;
  title: string;
  description?: string;
  actions?: React.ReactNode;
  back?: Crumb;
}) {
  return (
    <header className="mb-6">
      {back && (
        <Link href={back.href ?? "#"} className="btn-ghost mb-2 -ml-2 inline-flex text-xs">
          ← {back.label}
        </Link>
      )}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <p className="page-eyebrow">{eyebrow}</p>
          <h1 className="text-xl md:text-2xl font-semibold text-main mt-1">{title}</h1>
          {description && <p className="text-sm text-muted mt-1.5 max-w-2xl">{description}</p>}
        </div>
        {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
      </div>
    </header>
  );
}
