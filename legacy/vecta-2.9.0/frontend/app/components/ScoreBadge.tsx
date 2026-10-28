export default function ScoreBadge({ score, size = "md" }: { score: number; size?: "sm" | "md" }) {
  const priority = score >= 70;
  const meaning = priority ? "Priority" : score >= 40 ? "Standard pipeline" : "Archived, below 40";
  return (
    <span
      className={`score-badge ${priority ? "priority" : ""} ${size === "sm" ? "sm" : ""}`}
      role="img"
      aria-label={`VECTA Alignment Score ${score} out of 100 — ${meaning}`}
    >
      <span aria-hidden="true">{score}</span>
    </span>
  );
}
