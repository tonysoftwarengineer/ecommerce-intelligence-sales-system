import { Bar, BarChart, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { useReducedMotion } from "../hooks/useReducedMotion";
import { ChartTooltip } from "./ChartTooltip";

interface BreakdownBarChartProps {
  title: string;
  subtitle: string;
  data: Array<{ label: string; revenue: number }>;
  formatValue: (value: number) => string;
  formatCompact: (value: number) => string;
}

export function BreakdownBarChart({
  title,
  subtitle,
  data,
  formatValue,
  formatCompact,
}: BreakdownBarChartProps) {
  const animate = !useReducedMotion();

  return (
    <div className="card">
      <div className="card__head">
        <div>
          <h3 className="card__title">{title}</h3>
          <p className="card__sub">{subtitle}</p>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={296}>
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 72, bottom: 0, left: 0 }}>
          <XAxis type="number" hide />
          <YAxis
            type="category"
            dataKey="label"
            tick={{ fontSize: 11.5, fill: "rgba(255,255,255,0.6)" }}
            tickLine={false}
            axisLine={false}
            width={138}
          />
          <Tooltip
            content={<ChartTooltip formatValue={formatValue} />}
            cursor={{ fill: "rgba(255,255,255,0.04)" }}
          />
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
