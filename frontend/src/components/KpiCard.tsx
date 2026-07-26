import type { ReactNode } from "react";

import { useCountUp } from "../hooks/useCountUp";

interface KpiCardProps {
  label: string;
  value: number;
  format: (value: number) => string;
  hero?: boolean;
  children?: ReactNode;
}

export function KpiCard({ label, value, format, hero = false, children }: KpiCardProps) {
  const animated = useCountUp(value);

  return (
    <div className={`kpi${hero ? " kpi--hero" : ""}`}>
      <span className="kpi__label">{label}</span>
      <span className="kpi__value">{format(animated)}</span>
      {children}
    </div>
  );
}
