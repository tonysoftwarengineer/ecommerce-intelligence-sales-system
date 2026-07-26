export function formatCurrency(value: number): string {
  return `R$${value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

/** Axis-friendly short form: R$1.2M, R$847k, R$145 */
export function formatCompact(value: number): string {
  if (Math.abs(value) >= 1_000_000) return `R$${(value / 1_000_000).toFixed(1)}M`;
  if (Math.abs(value) >= 1_000) return `R$${Math.round(value / 1_000)}k`;
  return `R$${Math.round(value)}`;
}

/** Whole-Real form for hero figures, where cents are noise. */
export function formatWhole(value: number): string {
  return `R$${Math.round(value).toLocaleString("en-US")}`;
}

export function percentChange(current: number, previous: number): number | null {
  if (!previous) return null;
  return ((current - previous) / previous) * 100;
}
