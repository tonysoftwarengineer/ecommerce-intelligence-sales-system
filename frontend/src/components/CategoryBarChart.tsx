import { Bar, BarChart, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { useReducedMotion } from "../hooks/useReducedMotion";
import type { CategoryRevenue } from "../types";
import { formatCompact } from "../utils";
import { ChartTooltip } from "./ChartTooltip";

interface CategoryBarChartProps {
  data: CategoryRevenue[];
}

function prettify(category: string): string {
  return category.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function CategoryBarChart({ data }: CategoryBarChartProps) {
  const rows = data.map((d) => ({ ...d, label: prettify(d.category) }));
  const animate = !useReducedMotion();

  return (
    <div className="card">
      <div className="card__head">
        <div>
          <h3 className="card__title">Top Categories</h3>
          <p className="card__sub">By total revenue</p>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={296}>
        {/* No grid, no numeric axis: the value sits at the end of each bar, so
            both would be redundant ink competing with the data. */}
        <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 62, bottom: 0, left: 0 }}>
          <XAxis type="number" hide />
          <YAxis
            type="category"
            dataKey="label"
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
