import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

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
            dataKey="label"
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
