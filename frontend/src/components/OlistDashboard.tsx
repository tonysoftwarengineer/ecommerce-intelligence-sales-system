import { useEffect, useState } from "react";

import { fetchForecast, fetchReport, fetchSegments } from "../api";
import type { ForecastResponse, ReportResponse, SegmentsResponse } from "../types";
import { formatCurrency, formatWhole, percentChange } from "../utils";
import { CategoryBarChart } from "./CategoryBarChart";
import { DashboardHeader, DashboardStatus } from "./DashboardShell";
import { DeltaBadge } from "./DeltaBadge";
import { KpiCard } from "./KpiCard";
import { RevenueChart } from "./RevenueChart";
import { SegmentBreakdown } from "./SegmentBreakdown";
import { Sparkline } from "./Sparkline";
import { StateBarChart } from "./StateBarChart";
import { TopCustomersTable } from "./TopCustomersTable";

type DashboardState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | {
      status: "ready";
      report: ReportResponse;
      forecast: ForecastResponse;
      segments: SegmentsResponse;
    };

interface OlistDashboardProps {
  onBack: () => void;
}

export function OlistDashboard({ onBack }: OlistDashboardProps) {
  const [state, setState] = useState<DashboardState>({ status: "loading" });

  useEffect(() => {
    let active = true;
    Promise.all([fetchReport(), fetchForecast(), fetchSegments()])
      .then(([report, forecast, segments]) => {
        if (active) setState({ status: "ready", report, forecast, segments });
      })
      .catch((error: Error) => {
        if (active) setState({ status: "error", message: error.message });
      });
    return () => {
      active = false;
    };
  }, []);

  if (state.status === "loading") {
    return <DashboardStatus message="Loading Olist demo…" />;
  }

  if (state.status === "error") {
    return (
      <div className="status status--error">
        <p className="status__title">Couldn't reach the API</p>
        <p className="status__detail">
          Start the backend with <code>uvicorn api.main:app --port 8000</code>
        </p>
        <p className="status__detail status__detail--dim">{state.message}</p>
        <button type="button" className="button button--secondary" onClick={onBack}>
          Back to data sources
        </button>
      </div>
    );
  }

  const { report, forecast, segments } = state;
  const realMonths = report.revenue_by_month.filter((month) => !month.is_partial);
  const latest = realMonths.at(-1);
  const previous = realMonths.at(-2);
  const monthDelta = latest && previous ? percentChange(latest.revenue, previous.revenue) : null;
  const period = realMonths.length > 0 ? `${realMonths[0].month} → ${latest?.month}` : "";

  return (
    <div className="page">
      <DashboardHeader
        title="Sales Intelligence"
        period={period}
        context="Brazil · R$"
        onBack={onBack}
      />

      <section className="hero stagger" style={{ "--i": 0 } as React.CSSProperties}>
        <KpiCard label="Total Revenue" value={report.total_revenue} format={formatWhole} hero>
          <Sparkline values={realMonths.map((month) => month.revenue)} width={180} height={40} />
        </KpiCard>
        <KpiCard
          label="Average Order Value"
          value={report.average_order_value}
          format={formatCurrency}
        >
          <span className="kpi__note">Across all delivered &amp; shipped orders</span>
        </KpiCard>
        <KpiCard label="Latest Month" value={latest?.revenue ?? 0} format={formatWhole}>
          <DeltaBadge percent={monthDelta} caption="vs prior month" />
        </KpiCard>
      </section>

      <section className="stagger" style={{ "--i": 1 } as React.CSSProperties}>
        <RevenueChart months={realMonths} forecast={forecast.forecast} />
      </section>
      <section className="grid stagger" style={{ "--i": 2 } as React.CSSProperties}>
        <CategoryBarChart data={report.top_categories_by_revenue} />
        <StateBarChart data={report.revenue_by_state} />
      </section>
      <section className="grid stagger" style={{ "--i": 3 } as React.CSSProperties}>
        <TopCustomersTable data={report.top_customers_by_spend} />
        <SegmentBreakdown data={segments.segment_counts} />
      </section>
    </div>
  );
}
