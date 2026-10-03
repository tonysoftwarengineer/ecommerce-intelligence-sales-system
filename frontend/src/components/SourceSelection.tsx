interface SourceSelectionProps {
  onSelectUpload: () => void;
  onSelectSample: () => void;
}

export function SourceSelection({ onSelectUpload, onSelectSample }: SourceSelectionProps) {
  return (
    <main className="source-page">
      <div className="source-page__glow" aria-hidden="true" />
      <header className="source-header">
        <div className="header__brand">
          <span className="header__mark" aria-hidden="true" />
          <span className="source-header__brand">Sales Intelligence</span>
        </div>
        <span className="chip chip--accent">Evidence-backed sales analysis</span>
      </header>

      <section className="source-hero">
        <p className="eyebrow">Built for small online retailers</p>
        <h1>Understand what your sales data is saying.</h1>
        <p className="source-hero__copy">
          Upload your order export to see checked sales figures and changes over time.
          Forecasts appear only when the data supports them.
        </p>
      </section>

      <section className="source-grid" aria-label="Choose a data source">
        <button type="button" className="source-card source-card--primary" onClick={onSelectUpload}>
          <span className="source-card__icon" aria-hidden="true">↗</span>
          <span className="source-card__tag">Analyze your business</span>
          <strong>Upload a sales CSV</strong>
          <span>Tell us what your columns mean, check the results, and explore your sales.</span>
          <span className="source-card__action">Start analysis <span aria-hidden="true">→</span></span>
        </button>

        <button type="button" className="source-card" onClick={onSelectSample}>
          <span className="source-card__icon source-card__icon--muted" aria-hidden="true">◎</span>
          <span className="source-card__tag">No file needed · fictional data</span>
          <strong>Try a sample retailer</strong>
          <span>Review a small shop’s sample CSV in the same guided flow. No real customer data is used.</span>
          <span className="source-card__action source-card__action--muted">
            Try sample <span aria-hidden="true">→</span>
          </span>
        </button>
      </section>

      <footer className="source-trust">
        <span>CSV only in this release</span>
        <span>Raw files expire after 30 minutes</span>
        <span>Invalid rows are never silently dropped</span>
      </footer>
    </main>
  );
}
