import { useMemo } from "react";

import { downloadUrl } from "../api";
import type { GenericAnalysisResponse } from "../types";
import { createCurrencyFormatter, formatCount, percentChange } from "../utils";
import { BreakdownBarChart } from "./BreakdownBarChart";
import { DashboardHeader } from "./DashboardShell";
import { DeltaBadge } from "./DeltaBadge";
import { DiagnosticIntelligence } from "./DiagnosticIntelligence";
import { EvidenceSearchPanel } from "./EvidenceSearchPanel";
import { KpiCard } from "./KpiCard";
import { ProductDemandPanel } from "./ProductDemandPanel";
import { RevenueChart } from "./RevenueChart";
import { Sparkline } from "./Sparkline";

interface BusinessDashboardProps {
  analysis: GenericAnalysisResponse;
  onBack: () => void;
  onNewDataset: () => void;
  onCurrencyChange: (currency: string) => void;
}

export function BusinessDashboard({
  analysis,
  onBack,
  onNewDataset,
  onCurrencyChange,
}: BusinessDashboardProps) {
  const money = useMemo(() => createCurrencyFormatter(analysis.currency), [analysis.currency]);
  const wholeMoney = useMemo(
    () => createCurrencyFormatter(analysis.currency, { whole: true }),
    [analysis.currency],
  );
  const compactMoney = useMemo(
    () => createCurrencyFormatter(analysis.currency, { compact: true }),
    [analysis.currency],
  );
  const months = analysis.revenue_by_month;
  const latest = months.at(-1);
  const previous = months.at(-2);
  const delta = latest && previous ? percentChange(latest.revenue, previous.revenue) : null;
  const period = months.length > 0 ? `${months[0].month} → ${latest?.month}` : "";
  const forecastSubtitle = forecastDescription(analysis);

  return (
    <div className="page">
      <DashboardHeader
        title="Your Sales Intelligence"
        period={period}
        context={`${analysis.currency} · ${analysis.canonical_rows.toLocaleString()} valid rows`}
        onBack={onBack}
        actions={
          <div className="dashboard-actions">
            {analysis.available_currencies.length > 1 ? (
              <label className="currency-switcher">
                <span>Currency</span>
                <select
                  value={analysis.currency}
                  onChange={(event) => onCurrencyChange(event.target.value)}
                >
                  {analysis.available_currencies.map((currency) => (
                    <option value={currency} key={currency}>{currency}</option>
                  ))}
                </select>
              </label>
            ) : null}
            <button type="button" className="button button--small" onClick={onNewDataset}>
              New dataset
            </button>
          </div>
        }
      />

      <div className="analysis-strip" role="status">
        <span className="analysis-strip__file">{analysis.filename}</span>
        <span>{analysis.source_rows.toLocaleString()} source rows</span>
        <span className={analysis.quarantined_rows ? "text-warning" : "text-positive"}>
          {analysis.quarantined_rows.toLocaleString()} quarantined
        </span>
        <span>Session expires {formatExpiry(analysis.expires_at)}</span>
      </div>

      <DataQualityPanel analysis={analysis} />

      <section className="business-kpis stagger" style={{ "--i": 0 } as React.CSSProperties}>
        <KpiCard label="Net Revenue" value={analysis.kpis.net_revenue} format={wholeMoney} hero>
          <Sparkline values={months.map((month) => month.revenue)} width={180} height={40} />
          <DeltaBadge percent={delta} caption="latest revenue vs prior month" />
        </KpiCard>
        <KpiCard label="Gross Sales" value={analysis.kpis.gross_revenue} format={money} />
        <KpiCard label="Discounts" value={analysis.kpis.discount_amount} format={money} />
        <KpiCard label="Refunds" value={analysis.kpis.refund_amount} format={money}>
          <span className="kpi__note">Shown separately from gross sales</span>
        </KpiCard>
        <KpiCard label="Pending Sales" value={analysis.kpis.pending_value} format={money}>
          <span className="kpi__note">Not included in recognized revenue</span>
        </KpiCard>
        <KpiCard label="Average Order Value" value={analysis.kpis.average_order_value} format={money}>
          <span className="kpi__note">Net revenue per recognized order, including returns</span>
        </KpiCard>
        <KpiCard label="Orders" value={analysis.kpis.order_count} format={formatCount} />
      </section>

      <section className="stagger" style={{ "--i": 1 } as React.CSSProperties}>
        <DiagnosticIntelligence diagnostics={analysis.diagnostics} formatMoney={money} />
      </section>

      <section className="stagger" style={{ "--i": 2 } as React.CSSProperties}>
        <ProductDemandPanel
          analysisId={analysis.analysis_id}
          sourceDataDecisionReady={analysis.data_quality.decision_ready}
          hasProductCategories={analysis.capabilities.category_analysis}
        />
      </section>

      <section className="stagger" style={{ "--i": 3 } as React.CSSProperties}>
        <EvidenceSearchPanel analysisId={analysis.analysis_id} />
      </section>

      <section className="stagger" style={{ "--i": 4 } as React.CSSProperties}>
        <RevenueChart
          months={months}
          forecast={analysis.forecast.forecast}
          formatValue={money}
          formatAxis={compactMoney}
          subtitle={forecastSubtitle}
        />
      </section>

      <section className="grid stagger" style={{ "--i": 5 } as React.CSSProperties}>
        {analysis.capabilities.category_analysis ? (
          <BreakdownBarChart
            title="Top Categories"
            subtitle="By net revenue"
            data={analysis.top_categories.map((row) => ({
              label: row.category,
              revenue: row.revenue,
            }))}
            formatValue={money}
            formatCompact={compactMoney}
          />
        ) : (
          <UnavailableCard
            title="Category analysis unavailable"
            message="Map a product category column in your next upload to unlock this view."
          />
        )}

        {analysis.capabilities.regional_analysis ? (
          <BreakdownBarChart
            title="Revenue by Region"
            subtitle="Top regions by net revenue"
            data={analysis.revenue_by_region.map((row) => ({
              label: row.region,
              revenue: row.revenue,
            }))}
            formatValue={money}
            formatCompact={compactMoney}
          />
        ) : (
          <UnavailableCard
            title="Regional analysis unavailable"
            message="Map a state or region column in your next upload to unlock this view."
          />
        )}
      </section>

      <section className="grid stagger" style={{ "--i": 6 } as React.CSSProperties}>
        <TopBusinessCustomers customers={analysis.top_customers} formatValue={money} />
        <FinancialIntegrity analysis={analysis} formatValue={money} />
      </section>

      <section className="grid stagger" style={{ "--i": 7 } as React.CSSProperties}>
        <ForecastEvidence analysis={analysis} formatValue={money} />
        <OperationalSignals analysis={analysis} formatValue={money} />
      </section>

      <section className="delivery-card stagger" style={{ "--i": 8 } as React.CSSProperties}>
        <div>
          <p className="eyebrow">Audit-ready outputs</p>
          <h3>Take the processed data with you</h3>
          <p>
            The canonical file contains accepted rows. The quarantine file preserves rejected rows
            and their reasons, so no data-quality decision is hidden.
          </p>
        </div>
        <div className="delivery-card__actions">
          <a className="button" href={downloadUrl(analysis.downloads.canonical_csv)} download>
            Download canonical CSV
          </a>
          <a className="button button--secondary" href={downloadUrl(analysis.downloads.quarantine_csv)} download>
            Download quarantine CSV
          </a>
        </div>
      </section>

      {analysis.warnings.length > 0 ? (
        <aside className="notice notice--warning">
          <strong>Processing notes</strong>
          <ul>{analysis.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
        </aside>
      ) : null}
    </div>
  );
}

function forecastDescription(analysis: GenericAnalysisResponse): string {
  const forecast = analysis.forecast;
  if (analysis.data_quality.preview_only) {
    return "Preview only · forecast not calculated because source-data quality is too low";
  }
  if (forecast.status === "unavailable") {
    return `Historical trend · forecast unavailable with ${forecast.history_periods} complete months`;
  }
  const label = forecast.status === "experimental" ? "Experimental" : "Backtested";
  return `${label} ${forecast.horizon}-month forecast · chosen after comparing eligible methods: ${modelLabel(forecast.selected_model)}`;
}

function DataQualityPanel({ analysis }: { analysis: GenericAnalysisResponse }) {
  const quality = analysis.data_quality;
  if (quality.status === "normal" && quality.correction_actions.length === 0) {
    return null;
  }
  const heading = quality.preview_only
    ? "Preview Mode — correct the CSV before making decisions"
    : quality.status === "caution"
      ? "Data-quality caution"
      : "Data-quality note";
  return (
    <section className={`data-quality-panel data-quality-panel--${quality.status}`} aria-labelledby="data-quality-heading">
      <div className="data-quality-panel__head">
        <div>
          <p className="eyebrow">Source-data reliability</p>
          <h2 id="data-quality-heading">{heading}</h2>
        </div>
        <span className={`quality-badge quality-badge--${quality.status}`}>
          {quality.invalid_row_percentage.toFixed(1)}% invalid
        </span>
      </div>
      <p>{quality.message}</p>
      {quality.restricted_outputs.length > 0 ? (
        <p className="data-quality-panel__restriction">
          <strong>Not calculated:</strong> {quality.restricted_outputs.join(", ")}.
        </p>
      ) : null}
      {quality.correction_actions.length > 0 ? (
        <div className="data-quality-panel__actions">
          <h3>How to correct the CSV</h3>
          <ul className="repair-list">
            {quality.correction_actions.map((action) => (
              <li key={`${action.field}-${action.issue_code}-${action.problem}`}>
                <div className="repair-list__title">
                  <strong>{action.source_column ?? action.field.replaceAll("_", " ")}</strong>
                  <span>{action.affected_rows.toLocaleString()} affected row{action.affected_rows === 1 ? "" : "s"}</span>
                </div>
                <p>{action.problem}</p>
                <p><strong>Fix:</strong> {action.instruction}</p>
                {action.sample_row_numbers.length > 0 ? (
                  <small>{repairLocation(action)}</small>
                ) : null}
              </li>
            ))}
          </ul>
          <a className="button button--secondary" href={downloadUrl(analysis.downloads.quarantine_csv)} download>
            Download rows to correct
          </a>
        </div>
      ) : null}
    </section>
  );
}

function repairLocation(
  action: GenericAnalysisResponse["data_quality"]["correction_actions"][number],
): string {
  const column = action.source_column ?? action.field.replaceAll("_", " ");
  const location = csvRowLocations(action.sample_row_numbers, column);
  if (action.affected_rows > action.sample_row_numbers.length) {
    return `First ${action.sample_row_numbers.length} affected locations: ${location}. Download the quarantine CSV for all affected rows.`;
  }
  return `Affected location: ${location}.`;
}

function csvRowLocations(csvLineNumbers: number[], column: string): string {
  const lineNumbers = csvLineNumbers.join(", ");
  const dataRowNumbers = csvLineNumbers.map((lineNumber) => lineNumber - 1).join(", ");
  const lineLabel = csvLineNumbers.length === 1 ? "line" : "lines";
  const dataLabel = csvLineNumbers.length === 1 ? "row" : "rows";
  return `CSV ${lineLabel} ${lineNumbers} (data ${dataLabel} ${dataRowNumbers}) · ${column} column`;
}

function modelLabel(value: string | null): string {
  const labels: Record<string, string> = {
    latest_month: "Latest-month baseline",
    linear_trend: "Linear trend",
    moving_average_3: "3-month moving average",
    moving_average_6: "6-month moving average",
    linear_trend_recent_6: "Recent 6-month trend",
    seasonal_naive_12: "Same month last year",
  };
  return value === null ? "No model selected" : labels[value] ?? value.replaceAll("_", " ");
}

function formatExpiry(value: string): string {
  return new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(
    new Date(value),
  );
}

function TopBusinessCustomers({
  customers,
  formatValue,
}: {
  customers: GenericAnalysisResponse["top_customers"];
  formatValue: (value: number) => string;
}) {
  const max = Math.max(...customers.map((customer) => customer.revenue), 1);
  return (
    <div className="card">
      <div className="card__head">
        <div>
          <h3 className="card__title">Top Customers</h3>
          <p className="card__sub">By net lifetime revenue</p>
        </div>
      </div>
      <ol className="customers">
        {customers.map((customer, index) => (
          <li className="customers__row" key={customer.customer_id}>
            <span className="customers__rank">{index + 1}</span>
            <span className="customers__id" title={customer.customer_id}>
              {customer.customer_id.length > 12
                ? `${customer.customer_id.slice(0, 11)}…`
                : customer.customer_id}
            </span>
            <span className="customers__bar" aria-hidden="true">
              <span
                className="customers__bar-fill"
                style={{ width: `${Math.max((customer.revenue / max) * 100, 0)}%` }}
              />
            </span>
            <span className="customers__value">{formatValue(customer.revenue)}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function FinancialIntegrity({
  analysis,
  formatValue,
}: {
  analysis: GenericAnalysisResponse;
  formatValue: (value: number) => string;
}) {
  const { kpis } = analysis;
  return (
    <div className="card evidence-card">
      <div className="card__head">
        <div>
          <h3 className="card__title">Revenue Bridge</h3>
          <p className="card__sub">How gross sales become recognized net revenue</p>
        </div>
        <span className="quality-badge quality-badge--available">reconciled</span>
      </div>
      <div className="revenue-bridge" aria-label="Revenue calculation">
        <Metric label="Gross sales" value={formatValue(kpis.gross_revenue)} />
        <span>−</span>
        <Metric label="Discounts" value={formatValue(kpis.discount_amount)} />
        <span>−</span>
        <Metric label="Refunds" value={formatValue(kpis.refund_amount)} />
        <span>=</span>
        <Metric label="Net revenue" value={formatValue(kpis.net_revenue)} />
      </div>
      <p className="empty-state__copy">
        Tax and shipping stay separate from revenue, preserving a clear operational audit trail.
      </p>
    </div>
  );
}

function OperationalSignals({
  analysis,
  formatValue,
}: {
  analysis: GenericAnalysisResponse;
  formatValue: (value: number) => string;
}) {
  const { kpis } = analysis;
  return (
    <div className="card evidence-card">
      <div className="card__head">
        <div>
          <h3 className="card__title">Operational Signals</h3>
          <p className="card__sub">Amounts kept outside recognized sales</p>
        </div>
      </div>
      <div className="evidence-grid">
        <Metric label="Customers" value={formatCount(kpis.customer_count)} />
        <Metric label="Pending sales" value={formatValue(kpis.pending_value)} />
        <Metric label="Tax collected" value={formatValue(kpis.tax_collected)} />
        <Metric label="Shipping charged" value={formatValue(kpis.shipping_charged)} />
        <Metric label="Chargebacks" value={formatValue(kpis.chargeback_amount)} />
        <Metric label="Disputed value" value={formatValue(kpis.disputed_value)} />
        <Metric
          label="Net cash collected"
          value={kpis.net_collected === null ? "Unavailable" : formatValue(kpis.net_collected)}
        />
        {kpis.units_sold !== null ? (
          <Metric label="Units sold" value={formatCount(kpis.units_sold)} />
        ) : null}
        {kpis.units_returned !== null ? (
          <Metric label="Units returned" value={formatCount(kpis.units_returned)} />
        ) : null}
      </div>
      {kpis.net_collected === null ? (
        <p className="empty-state__copy">Map a payment amount column to calculate cash collected. Payment status alone is not enough evidence.</p>
      ) : null}
    </div>
  );
}

function ForecastEvidence({
  analysis,
  formatValue,
}: {
  analysis: GenericAnalysisResponse;
  formatValue: (value: number) => string;
}) {
  const { forecast } = analysis;
  const trustLevel = forecast.trust_level ?? legacyTrustLevel(forecast.status);
  const trustMessage = forecast.trust_message ?? legacyTrustMessage(forecast.status);
  const modelEvaluations = forecast.model_evaluations ?? [];
  return (
    <div className="card evidence-card">
      <div className="card__head">
        <div>
          <h3 className="card__title">Forecast Evidence</h3>
          <p className="card__sub">How the forecast was chosen and how much confidence it deserves</p>
        </div>
        <div className="forecast-badges">
          <span className={`quality-badge quality-badge--${trustLevel}`}>
            {trustLevel} trust
          </span>
          <span className={`quality-badge quality-badge--${forecast.status}`}>{forecast.status}</span>
        </div>
      </div>

      {forecast.backtest_metrics ? (
        <>
          <p className="empty-state__copy">
            {trustMessage}
          </p>
          <div className="evidence-grid">
            <Metric label="Chosen method" value={modelLabel(forecast.selected_model)} />
            <Metric label="Rolling tests" value={forecast.backtest_folds.toString()} />
            <Metric label="Mean error" value={formatValue(forecast.backtest_metrics.mae)} />
            <Metric
              label="WAPE"
              value={
                forecast.backtest_metrics.wape_percent === null
                  ? "Not defined"
                  : `${forecast.backtest_metrics.wape_percent.toFixed(1)}%`
              }
            />
          </div>
          {forecast.selection_reason ? (
            <p className="forecast-selection-reason"><strong>Why this method:</strong> {forecast.selection_reason}</p>
          ) : null}
          {modelEvaluations.length > 0 ? (
            <div className="forecast-comparison">
              <p className="forecast-comparison__title">Methods tested</p>
              <div className="forecast-comparison__table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Method</th>
                      <th>Mean error</th>
                      <th>WAPE</th>
                      <th>Result</th>
                    </tr>
                  </thead>
                  <tbody>
                    {modelEvaluations.map((evaluation) => (
                      <tr key={evaluation.model} className={evaluation.selected ? "is-selected" : undefined}>
                        <td>{modelLabel(evaluation.model)}</td>
                        <td>{formatValue(evaluation.metrics.mae)}</td>
                        <td>
                          {evaluation.metrics.wape_percent === null
                            ? "Not defined"
                            : `${evaluation.metrics.wape_percent.toFixed(1)}%`}
                        </td>
                        <td>{evaluation.selected ? "Chosen" : "Compared"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : null}
        </>
      ) : (
        <p className="empty-state__copy">{trustMessage}</p>
      )}

      {forecast.backtest_metrics?.wape_percent !== null && forecast.backtest_metrics?.wape_percent !== undefined && forecast.backtest_metrics.wape_percent > 25 ? (
        <p className="classification__warning"><strong>High error:</strong> this backtest missed historical revenue by {forecast.backtest_metrics.wape_percent.toFixed(1)}% in aggregate. Use this forecast for exploration, not commitments.</p>
      ) : null}

      {forecast.limitations.length > 0 ? (
        <ul className="limitations">
          {forecast.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}
        </ul>
      ) : null}
    </div>
  );
}

function legacyTrustLevel(status: GenericAnalysisResponse["forecast"]["status"]): string {
  if (status === "unavailable") return "unavailable";
  return status === "experimental" ? "limited" : "exploratory";
}

function legacyTrustMessage(status: GenericAnalysisResponse["forecast"]["status"]): string {
  if (status === "unavailable") {
    return "Forecast unavailable. Review the listed data limitations before trying again.";
  }
  if (status === "experimental") {
    return "Limited history: use this forecast for exploration, not commitments.";
  }
  return "This saved analysis predates the detailed trust assessment. Run the analysis again to compare the tested methods.";
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="evidence-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function UnavailableCard({ title, message }: { title: string; message: string }) {
  return (
    <div className="card unavailable-card">
      <span className="unavailable-card__icon" aria-hidden="true">＋</span>
      <h3 className="card__title">{title}</h3>
      <p className="empty-state__copy">{message}</p>
    </div>
  );
}
