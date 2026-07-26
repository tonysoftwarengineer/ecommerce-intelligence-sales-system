interface DeltaBadgeProps {
  percent: number | null;
  caption: string;
}

export function DeltaBadge({ percent, caption }: DeltaBadgeProps) {
  if (percent === null) return null;

  const positive = percent >= 0;

  return (
    <div className={`delta ${positive ? "delta--up" : "delta--down"}`}>
      <span className="delta__arrow" aria-hidden="true">
        {positive ? "▲" : "▼"}
      </span>
      <span className="delta__value">
        {positive ? "+" : ""}
        {percent.toFixed(1)}%
      </span>
      <span className="delta__caption">{caption}</span>
    </div>
  );
}
