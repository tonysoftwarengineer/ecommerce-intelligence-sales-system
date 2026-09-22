import { formatCurrency } from "../utils";

interface TooltipEntry {
  name?: string;
  dataKey?: string | number;
  value?: number;
  color?: string;
}

interface ChartTooltipProps {
  active?: boolean;
  payload?: TooltipEntry[];
  label?: string;
  formatValue?: (value: number) => string;
  forecastBoundaryLabel?: string;
}

const LABELS: Record<string, string> = {
  revenue: "Revenue",
  forecast: "Forecast",
};

export function ChartTooltip({
  active,
  payload,
  label,
  formatValue = formatCurrency,
  forecastBoundaryLabel,
}: ChartTooltipProps) {
  if (!active || !payload?.length) return null;

  const isForecastBoundary = Boolean(forecastBoundaryLabel && label === forecastBoundaryLabel);
  const rows = payload.filter(
    (entry) => entry.value != null && !(isForecastBoundary && entry.dataKey === "forecast"),
  );
  if (!rows.length) return null;

  return (
    <div className="tooltip">
      <div className="tooltip__label">{label}</div>
      {rows.map((entry) => (
        <div className="tooltip__row" key={String(entry.dataKey)}>
          <span className="tooltip__dot" style={{ background: entry.color }} />
          <span className="tooltip__name">{LABELS[String(entry.dataKey)] ?? entry.name}</span>
          <span className="tooltip__value">{formatValue(entry.value as number)}</span>
        </div>
      ))}
      {isForecastBoundary ? (
        <div className="tooltip__note">Forecast begins next month.</div>
      ) : null}
    </div>
  );
}
