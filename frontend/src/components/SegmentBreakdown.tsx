import type { SegmentCount } from "../types";

interface SegmentBreakdownProps {
  data: SegmentCount[];
}

// Fixed assignment order, never cycled. Validated against the dark surface
// (validate_palette.js, all six checks pass).
const ORDER = ["High Value", "Regular", "At Risk", "New/Occasional"];
const COLORS: Record<string, string> = {
  "High Value": "var(--seg-3)",
  Regular: "var(--seg-1)",
  "At Risk": "var(--seg-2)",
  "New/Occasional": "var(--seg-4)",
};

export function SegmentBreakdown({ data }: SegmentBreakdownProps) {
  const sorted = [...data].sort(
    (a, b) => ORDER.indexOf(a.segment_label) - ORDER.indexOf(b.segment_label),
  );
  const total = sorted.reduce((sum, segment) => sum + segment.customer_count, 0);

  return (
    <div className="card">
      <div className="card__head">
        <div>
          <h3 className="card__title">Customer Segments</h3>
          <p className="card__sub">{total.toLocaleString()} customers, RFM + k-means</p>
        </div>
      </div>

      <div className="segbar" role="img" aria-label="Customer segment distribution">
        {sorted.map((segment) => (
          <span
            key={segment.segment_label}
            className="segbar__part"
            style={{
              width: `${(segment.customer_count / total) * 100}%`,
              background: COLORS[segment.segment_label] ?? "var(--text-muted)",
            }}
          />
        ))}
      </div>

      <ul className="seglist">
        {sorted.map((segment) => (
          <li className="seglist__item" key={segment.segment_label}>
            <span
              className="seglist__dot"
              style={{ background: COLORS[segment.segment_label] ?? "var(--text-muted)" }}
            />
            <span className="seglist__label">{segment.segment_label}</span>
            <span className="seglist__pct">
              {((segment.customer_count / total) * 100).toFixed(1)}%
            </span>
            <span className="seglist__count">{segment.customer_count.toLocaleString()}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
