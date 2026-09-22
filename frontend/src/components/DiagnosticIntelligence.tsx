import type { DiagnosticEvidence, DiagnosticReport } from "../types";
import { formatCount } from "../utils";

interface DiagnosticIntelligenceProps {
  diagnostics: {
    comparison: DiagnosticReport;
    anomalies: DiagnosticReport;
  };
  formatMoney: (value: number) => string;
}

export function DiagnosticIntelligence({
  diagnostics,
  formatMoney,
}: DiagnosticIntelligenceProps) {
  return (
    <section className="diagnostic-intelligence" aria-labelledby="diagnostic-intelligence-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Decision intelligence</p>
          <h2 id="diagnostic-intelligence-title">What changed and what to review</h2>
          <p>
            Findings use validated data. Recommendations are investigation prompts and require
            human review.
          </p>
        </div>
      </div>
      <div className="diagnostic-grid">
        <DiagnosticSection
          title="Latest performance change"
          subtitle="A comparison of the two latest complete months"
          report={diagnostics.comparison}
          formatMoney={formatMoney}
        />
        <DiagnosticSection
          title="Unusual changes"
          subtitle="Compared with a six-month historical baseline"
          report={diagnostics.anomalies}
          formatMoney={formatMoney}
        />
      </div>
    </section>
  );
}

function DiagnosticSection({
  title,
  subtitle,
  report,
  formatMoney,
}: {
  title: string;
  subtitle: string;
  report: DiagnosticReport;
  formatMoney: (value: number) => string;
}) {
  return (
    <article className="card diagnostic-card">
      <div className="card__head">
        <div>
          <h3 className="card__title">{title}</h3>
          <p className="card__sub">{subtitle}</p>
        </div>
        <span className={`quality-badge quality-badge--${report.status}`}>
          {statusLabel(report.status)}
        </span>
      </div>

      {report.status === "unavailable" ? (
        <UnavailableDiagnostics limitations={report.unavailable_capabilities} />
      ) : report.status === "no_findings" ? (
        <p className="empty-state__copy">
          No unusual changes were detected with the available complete history.
        </p>
      ) : (
        <div className="diagnostic-findings">
          {report.insights.map((insight) => (
            <article className="diagnostic-finding" key={insight.id}>
              <div className="diagnostic-finding__head">
                <div>
                  <h4>{insight.title}</h4>
                  <p>{insight.observation}</p>
                </div>
                <div className="diagnostic-finding__badges">
                  <span className={`priority priority--${insight.priority}`}>
                    {insight.priority} priority
                  </span>
                  <span className="confidence">{insight.confidence} confidence</span>
                </div>
              </div>

              <div className="diagnostic-evidence" aria-label={`${insight.title} evidence`}>
                {insight.evidence.map((evidence) => (
                  <Evidence key={evidence.metric} evidence={evidence} formatMoney={formatMoney} />
                ))}
              </div>

              {insight.recommended_action ? (
                <div className="recommendation">
                  <div>
                    <span className="recommendation__eyebrow">Suggested investigation</span>
                    <h5>{insight.recommended_action.title}</h5>
                    <p>{insight.recommended_action.description}</p>
                  </div>
                  <div className="recommendation__meta">
                    <span>Human review required</span>
                    {insight.recommended_action.score ? (
                      <span title="Impact + urgency + confidence">
                        Score {insight.recommended_action.score.total}/9
                      </span>
                    ) : null}
                  </div>
                </div>
              ) : null}

              {insight.limitations.length > 0 ? (
                <ul className="diagnostic-limitations">
                  {insight.limitations.map((limitation) => (
                    <li key={limitation.code}>{limitation.message}</li>
                  ))}
                </ul>
              ) : null}
            </article>
          ))}
        </div>
      )}
    </article>
  );
}

function Evidence({
  evidence,
  formatMoney,
}: {
  evidence: DiagnosticEvidence;
  formatMoney: (value: number) => string;
}) {
  return (
    <div className="diagnostic-evidence__item">
      <span>{metricLabel(evidence.metric)}</span>
      <strong>{formatEvidenceValue(evidence.current_value, evidence.unit, formatMoney)}</strong>
      {evidence.percent_change !== null ? (
        <small className={evidence.percent_change < 0 ? "text-negative" : "text-positive"}>
          {evidence.percent_change > 0 ? "+" : ""}
          {evidence.percent_change.toFixed(1)}% vs baseline
        </small>
      ) : null}
    </div>
  );
}

function UnavailableDiagnostics({ limitations }: { limitations: DiagnosticReport["unavailable_capabilities"] }) {
  return (
    <div className="diagnostic-unavailable">
      <p className="empty-state__copy">This diagnostic cannot be assessed reliably yet.</p>
      <ul className="diagnostic-limitations">
        {limitations.map((limitation) => <li key={limitation.code}>{limitation.message}</li>)}
      </ul>
    </div>
  );
}

function formatEvidenceValue(
  value: number,
  unit: string,
  formatMoney: (value: number) => string,
): string {
  return unit === "orders" ? formatCount(value) : formatMoney(value);
}

function metricLabel(metric: string): string {
  return metric.replaceAll("_", " ");
}

function statusLabel(status: DiagnosticReport["status"]): string {
  if (status === "no_findings") return "No unusual changes";
  return status;
}
