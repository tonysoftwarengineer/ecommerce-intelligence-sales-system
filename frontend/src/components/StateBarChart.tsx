import { Bar, BarChart, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

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
  const shown = rows.reduce((sum, r) => sum + r.revenue, 0);
  const total = data.reduce((sum, r) => sum + r.revenue, 0);

  return (
    <div className="card">
      <div className="card__head">
        <div>
          <h3 className="card__title">Revenue by State</h3>
          <p className="card__sub">
            Top {TOP_N} of {data.length} · {((shown / total) * 100).toFixed(0)}% of revenue
          </p>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={296}>
        <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 62, bottom: 0, left: 0 }}>
          <XAxis type="number" hide />
          <YAxis
            type="category"
            dataKey="state_name"
            tick={{ fontSize: 11.5, fill: "rgba(255,255,255,0.6)" }}
            tickLine={false}
            axisLine={false}
            width={138}
          />
          <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
          <Bar
            dataKey="revenue"
            fill="#3987e5"
            radius={[0, 4, 4, 0]}
            barSize={15}
            isAnimationActive={animate}
            animationDuration={800}
          >
            <LabelList
              dataKey="revenue"
              position="right"
              offset={10}
              formatter={(value: unknown) => formatCompact(Number(value))}
              fill="rgba(255,255,255,0.55)"
              fontSize={11}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
