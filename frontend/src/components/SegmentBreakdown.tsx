import type { SegmentSummary } from "../types";
import { formatCompact } from "../utils";

interface SegmentBreakdownProps {
  data: SegmentSummary[];
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
          <p className="card__sub">{total.toLocaleString()} customers · RFM + k-means</p>
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

      <div className="segtable-scroll">
        <table className="segtable">
          <thead>
            <tr>
              <th>Segment</th>
              <th>Share</th>
              <th>Orders</th>
              <th>Avg spend</th>
              <th>Last seen</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((segment) => (
              <tr key={segment.segment_label}>
                <td className="segtable__name">
                  <span
                    className="seglist__dot"
                    style={{ background: COLORS[segment.segment_label] ?? "var(--text-muted)" }}
                  />
                  {segment.segment_label}
                </td>
                <td>{((segment.customer_count / total) * 100).toFixed(1)}%</td>
                <td>{segment.avg_frequency.toFixed(2)}</td>
                <td>{formatCompact(segment.avg_monetary)}</td>
                <td className="segtable__dim">{Math.round(segment.avg_recency)}d</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="segnote">
        Only <strong>High Value</strong> customers order more than once — every other segment
        averages a single order.
      </p>
    </div>
  );
}
