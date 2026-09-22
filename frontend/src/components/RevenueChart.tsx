import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useReducedMotion } from "../hooks/useReducedMotion";
import type { ForecastPoint } from "../types";
import { formatCompact } from "../utils";
import { ChartTooltip } from "./ChartTooltip";

interface RevenueChartProps {
  months: Array<{ month: string; revenue: number }>;
  forecast: ForecastPoint[];
  formatValue?: (value: number) => string;
  formatAxis?: (value: number) => string;
  subtitle?: string;
}

interface Row {
  month: string;
  revenue: number | null;
  forecast: number | null;
}

/** Actual and forecast are one entity (revenue) shown in two states, so they
 *  share a hue and differ by treatment (dashed, dimmed) rather than by color.
 *  When a real forecast exists, the last actual month also carries a forecast
 *  value so the dashed line starts attached to the solid one. */
function buildRows(months: Array<{ month: string; revenue: number }>, forecast: ForecastPoint[]): Row[] {
  const actual: Row[] = months.map((m) => ({
    month: m.month,
    revenue: m.revenue,
    forecast: null,
  }));

  const last = actual[actual.length - 1];
  if (last && forecast.length > 0) last.forecast = last.revenue;

  const predicted: Row[] = forecast.map((point) => ({
    month: point.month,
    revenue: null,
    forecast: point.predicted_revenue,
  }));

  return [...actual, ...predicted];
}

export function RevenueChart({
  months,
  forecast,
  formatValue,
  formatAxis = formatCompact,
  subtitle,
}: RevenueChartProps) {
  const rows = buildRows(months, forecast);
  const animate = !useReducedMotion();
  const boundary = months[months.length - 1]?.month;

  return (
    <div className="card card--wide">
      <div className="card__head">
        <div>
          <h3 className="card__title">Revenue Trend</h3>
          <p className="card__sub">
            {subtitle ?? `Monthly revenue with ${forecast.length}-month forecast`}
          </p>
        </div>
        <div className="legend" aria-label="Chart legend">
          <span className="legend__item">
            <span className="legend__swatch" /> Actual
          </span>
          {forecast.length > 0 ? (
            <span className="legend__item">
              <span className="legend__swatch legend__swatch--dashed" /> Forecast
            </span>
          ) : null}
        </div>
      </div>

      {boundary && forecast.length > 0 ? (
        <p className="forecast-boundary-note">
          Actual data ends in {boundary}. Forecast begins the following month.
        </p>
      ) : null}

      <ResponsiveContainer width="100%" height={300}>
        <ComposedChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="revenueFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#3987e5" stopOpacity={0.32} />
              <stop offset="100%" stopColor="#3987e5" stopOpacity={0} />
            </linearGradient>
          </defs>

          <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
          <XAxis
            dataKey="month"
            tick={{ fontSize: 11, fill: "rgba(255,255,255,0.38)" }}
            tickLine={false}
            axisLine={{ stroke: "rgba(255,255,255,0.07)" }}
            interval="preserveStartEnd"
            minTickGap={24}
          />
          <YAxis
            tick={{ fontSize: 11, fill: "rgba(255,255,255,0.38)" }}
            tickLine={false}
            axisLine={false}
            tickFormatter={formatAxis}
            width={64}
          />
          <Tooltip
            content={(
              <ChartTooltip
                formatValue={formatValue}
                forecastBoundaryLabel={boundary}
              />
            )}
            cursor={{ stroke: "rgba(255,255,255,0.18)", strokeWidth: 1 }}
          />

          {/* The area fill necessarily stops where measured data stops. Marking
              that boundary turns an unavoidable hard edge into the useful fact
              it actually represents: everything right of here is predicted. */}
          {boundary && forecast.length > 0 ? (
            <ReferenceLine
              x={boundary}
              stroke="rgba(255,255,255,0.18)"
              strokeDasharray="3 3"
              label={{
                value: `Forecast begins after ${boundary}`,
                position: "insideTopRight",
                fill: "rgba(255,255,255,0.38)",
                fontSize: 11,
                offset: 10,
              }}
            />
          ) : null}

          <Area
            type="monotone"
            dataKey="revenue"
            stroke="#3987e5"
            strokeWidth={2}
            fill="url(#revenueFill)"
            dot={false}
            activeDot={{ r: 4, strokeWidth: 2, stroke: "#16161a" }}
            isAnimationActive={animate}
            animationDuration={900}
          />
          <Line
            type="monotone"
            dataKey="forecast"
            stroke="#3987e5"
            strokeWidth={2}
            strokeDasharray="5 4"
            strokeOpacity={0.72}
            dot={false}
            activeDot={{ r: 4, strokeWidth: 2, stroke: "#16161a" }}
            isAnimationActive={animate}
            animationDuration={900}
            animationBegin={400}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
