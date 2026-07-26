import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { useReducedMotion } from "../hooks/useReducedMotion";
import type { StateRevenue } from "../types";
import { formatCompact } from "../utils";
import { ChartTooltip } from "./ChartTooltip";

interface StateBarChartProps {
  data: StateRevenue[];
}

const TOP_N = 10;

export function StateBarChart({ data }: StateBarChartProps) {
  // 27 states at readable type would need a scrollbar or 8px labels. The tail
  // is tiny (Roraima is 0.06% of revenue), so show the meaningful head and say
  // so in the subtitle rather than cramming everything in.
  const rows = data.slice(0, TOP_N);
  const animate = !useReducedMotion();

  return (
    <div className="card">
      <div className="card__head">
        <div>
          <h3 className="card__title">Revenue by State</h3>
          <p className="card__sub">
            Top {TOP_N} of {data.length} Brazilian states
          </p>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
          <CartesianGrid stroke="rgba(255,255,255,0.06)" horizontal={false} />
          <XAxis
            type="number"
            tick={{ fontSize: 11, fill: "rgba(255,255,255,0.38)" }}
            tickLine={false}
            axisLine={false}
            tickFormatter={formatCompact}
          />
          <YAxis
            type="category"
            dataKey="state_name"
            tick={{ fontSize: 11, fill: "rgba(255,255,255,0.6)" }}
            tickLine={false}
            axisLine={false}
            width={140}
          />
          <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
          <Bar
            dataKey="revenue"
            fill="#3987e5"
            radius={[0, 4, 4, 0]}
            barSize={14}
            isAnimationActive={animate}
            animationDuration={800}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
