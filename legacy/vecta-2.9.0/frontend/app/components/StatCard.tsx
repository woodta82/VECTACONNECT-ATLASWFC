export default function StatCard({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "default" | "accent" | "danger";
}) {
  const valueColor = tone === "accent" ? "text-accent" : tone === "danger" ? "" : "text-main";
  return (
    <div
      className="panel p-5 text-center overflow-hidden"
      style={tone === "accent" ? { borderColor: "var(--accent)" } : undefined}
    >
      <p className="text-xs font-semibold uppercase tracking-wide text-muted truncate">{label}</p>
      <p
        className="font-bold mt-2 font-display leading-tight"
        style={{
          fontSize: "clamp(1.1rem, 5vw, 1.75rem)",
          ...(tone === "danger" ? { color: "var(--danger)" } : {}),
        }}
      >
        <span className={valueColor}>{value}</span>
      </p>
      {hint && <p className="text-xs text-muted mt-1.5">{hint}</p>}
    </div>
  );
}
