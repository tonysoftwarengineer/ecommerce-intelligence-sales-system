import { useEffect, useState } from "react";

import "./App.css";
import { fetchForecast, fetchReport, fetchSegments } from "./api";
import { CategoryBarChart } from "./components/CategoryBarChart";
import { DeltaBadge } from "./components/DeltaBadge";
import { KpiCard } from "./components/KpiCard";
import { RevenueChart } from "./components/RevenueChart";
import { SegmentBreakdown } from "./components/SegmentBreakdown";
import { Sparkline } from "./components/Sparkline";
import { StateBarChart } from "./components/StateBarChart";
import { TopCustomersTable } from "./components/TopCustomersTable";
import type { ForecastResponse, ReportResponse, SegmentsResponse } from "./types";
import { formatCurrency, formatWhole, percentChange } from "./utils";

type DashboardState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | {
      status: "ready";
      report: ReportResponse;
      forecast: ForecastResponse;
      segments: SegmentsResponse;
    };

function App() {
  const [state, setState] = useState<DashboardState>({ status: "loading" });

  useEffect(() => {
    Promise.all([fetchReport(), fetchForecast(), fetchSegments()])
      .then(([report, forecast, segments]) =>
        setState({ status: "ready", report, forecast, segments }),
      )
      .catch((error: Error) => setState({ status: "error", message: error.message }));
  }, []);

  if (state.status === "loading") {
    return (
      <div className="status">
        <div className="spinner" />
        <p>Loading dashboard…</p>
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="status status--error">
        <p className="status__title">Couldn't reach the API</p>
        <p className="status__detail">
          Is the backend running on localhost:8000? Start it with{" "}
          <code>uvicorn api.main:app --port 8000</code>
        </p>
        <p className="status__detail status__detail--dim">{state.message}</p>
      </div>
    );
  }

  const { report, forecast, segments } = state;

  // Partial months are dataset-boundary artifacts, not real trend — the same
  // judgment the forecast model already makes. Flagged server-side.
  const realMonths = report.revenue_by_month.filter((m) => !m.is_partial);
  const latest = realMonths[realMonths.length - 1];
  const previous = realMonths[realMonths.length - 2];
  const monthDelta = latest && previous ? percentChange(latest.revenue, previous.revenue) : null;

  const period =
    realMonths.length > 0 ? `${realMonths[0].month} → ${latest.month}` : "";

  return (
    <div className="page">
      <header className="header">
        <div className="header__brand">
          <span className="header__mark" aria-hidden="true" />
          <h1 className="header__title">Sales Intelligence</h1>
        </div>
        <div className="header__meta">
          <span className="chip">{period}</span>
          <span className="chip chip--accent">Brazil · R$</span>
        </div>
      </header>

      <section className="hero stagger" style={{ "--i": 0 } as React.CSSProperties}>
        <KpiCard label="Total Revenue" value={report.total_revenue} format={formatWhole} hero>
          <Sparkline values={realMonths.map((m) => m.revenue)} width={180} height={40} />
        </KpiCard>

        <KpiCard label="Average Order Value" value={report.average_order_value} format={formatCurrency}>
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

export default App;
