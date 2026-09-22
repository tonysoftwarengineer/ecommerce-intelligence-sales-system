interface SourceSelectionProps {
  onSelectOlist: () => void;
  onSelectUpload: () => void;
}

export function SourceSelection({ onSelectOlist, onSelectUpload }: SourceSelectionProps) {
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
          Upload an order export, review its columns, and see validated sales changes and
          investigation prompts. Forecasts appear only when their data checks pass.
        </p>
      </section>

      <section className="source-grid" aria-label="Choose a data source">
        <button type="button" className="source-card source-card--primary" onClick={onSelectUpload}>
          <span className="source-card__icon" aria-hidden="true">↗</span>
          <span className="source-card__tag">Analyze your business</span>
          <strong>Upload a sales CSV</strong>
          <span>Map your columns, verify data quality, and explore a private sales dashboard.</span>
          <span className="source-card__action">Start analysis <span aria-hidden="true">→</span></span>
        </button>

        <button type="button" className="source-card" onClick={onSelectOlist}>
          <span className="source-card__icon source-card__icon--muted" aria-hidden="true">◎</span>
          <span className="source-card__tag">Product demonstration</span>
          <strong>Explore the Olist demo</strong>
          <span>Open the pre-built Brazilian ecommerce dashboard and model outputs.</span>
          <span className="source-card__action source-card__action--muted">
            View demo <span aria-hidden="true">→</span>
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
