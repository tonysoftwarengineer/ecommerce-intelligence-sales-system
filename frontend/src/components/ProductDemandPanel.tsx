import { useState } from "react";

import { analyzeProductDemand } from "../api";
import type {
  ProductDemandCategory,
  ProductDemandProduct,
  ProductDemandRequest,
  ProductDemandResponse,
} from "../types";

const PRODUCT_PAGE_SIZE = 20;

interface ProductDemandPanelProps {
  analysisId: string;
  sourceDataDecisionReady: boolean;
  hasProductCategories: boolean;
}

export function ProductDemandPanel({
  analysisId,
  sourceDataDecisionReady,
  hasProductCategories,
}: ProductDemandPanelProps) {
  const [coversAllOpenDays, setCoversAllOpenDays] = useState(false);
  const [noUnrecordedStockouts, setNoUnrecordedStockouts] = useState(false);
  const [confirmNamesUnique, setConfirmNamesUnique] = useState(false);
  const [confirmCategories, setConfirmCategories] = useState(false);
  const [defaultUnit, setDefaultUnit] = useState("");
  const [closedDates, setClosedDates] = useState("");
  const [result, setResult] = useState<ProductDemandResponse | null>(null);
  const [visiblePreviews, setVisiblePreviews] = useState(PRODUCT_PAGE_SIZE);
  const [visibleUnavailable, setVisibleUnavailable] = useState(PRODUCT_PAGE_SIZE);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runProductDemand() {
    setBusy(true);
    setError(null);
    try {
      const request: ProductDemandRequest = {
        confirm_product_names_unique: confirmNamesUnique,
        confirm_product_categories: confirmCategories,
        export_covers_all_open_days: coversAllOpenDays,
        stockout_tracking_complete: noUnrecordedStockouts,
        business_closed_dates: parseDateList(closedDates),
        stockout_dates: [],
        ...(defaultUnit.trim() ? { default_unit_of_measure: defaultUnit.trim() } : {}),
      };
      setResult(await analyzeProductDemand(analysisId, request));
      setVisiblePreviews(PRODUCT_PAGE_SIZE);
      setVisibleUnavailable(PRODUCT_PAGE_SIZE);
    } catch (requestError) {
      setError(messageFrom(requestError));
    } finally {
      setBusy(false);
    }
  }

  function invalidateResult() {
    setResult(null);
    setError(null);
  }

  const previewProducts = result?.products.filter((product) => product.forecast !== null) ?? [];
  const unavailableProducts =
    result?.products.filter((product) => product.forecast === null) ?? [];
  const previewCategories =
    result?.categories.filter((category) => category.forecast !== null) ?? [];
  const unavailableCategories =
    result?.categories.filter((category) => category.forecast === null) ?? [];

  return (
    <section className="product-demand" aria-labelledby="product-demand-heading">
      <div className="product-demand__head">
        <div>
          <p className="eyebrow">Product demand · experimental</p>
          <h2 id="product-demand-heading">Plan the next seven days by product</h2>
          <p>
            The engine evaluates each product separately and only shows a fulfilled-unit estimate
            when its history passes the preview rules. These estimates are for exploration, not
            restocking commitments; sparse-product reliability remains unproven.
          </p>
        </div>
        <span className="quality-badge quality-badge--limited">Preview only</span>
      </div>

      {!sourceDataDecisionReady ? (
        <div className="notice notice--error" role="status">
          <strong>Product-demand forecast unavailable</strong>
          <p>
            The source-data quality gate has restricted forecasting. Correct the quarantined CSV
            rows and run the analysis again.
          </p>
        </div>
      ) : (
        <div className="product-demand__setup">
          <div>
            <h3>Confirm the history before evaluation</h3>
            <p>
              These confirmations stop missing rows from being silently interpreted as zero sales.
            </p>
          </div>

          <label className="confirmation-box product-demand__confirmation">
            <input
              type="checkbox"
              checked={coversAllOpenDays}
              onChange={(event) => {
                setCoversAllOpenDays(event.target.checked);
                invalidateResult();
              }}
            />
            <span>
              <strong>The export covers every open business day</strong>
              Days with no product row can be treated as zero sales. Add any closed dates below.
            </span>
          </label>

          {hasProductCategories ? (
            <label className="confirmation-box product-demand__confirmation">
              <input
                type="checkbox"
                checked={confirmCategories}
                onChange={(event) => {
                  setConfirmCategories(event.target.checked);
                  invalidateResult();
                }}
              />
              <span>
                <strong>The mapped product categories are correct</strong>
                This enables a category-level fallback only when every product in that category
                fails the product forecast checks.
              </span>
            </label>
          ) : null}

          <label className="confirmation-box product-demand__confirmation">
            <input
              type="checkbox"
              checked={noUnrecordedStockouts}
              onChange={(event) => {
                setNoUnrecordedStockouts(event.target.checked);
                invalidateResult();
              }}
            />
            <span>
              <strong>There were no unrecorded stockout days</strong>
              Do not confirm this when products were unavailable for sale but those dates are not
              identified in the data.
            </span>
          </label>

          <details className="product-demand__optional">
            <summary>Optional identity, unit and closure details</summary>
            <div className="settings-grid">
              <label className="field">
                <span className="form-label">Default unit of measure</span>
                <input
                  value={defaultUnit}
                  onChange={(event) => {
                    setDefaultUnit(event.target.value);
                    invalidateResult();
                  }}
                  placeholder="piece"
                />
                <small>Used only when the CSV has no unit column.</small>
              </label>
              <label className="field">
                <span className="form-label">Closed dates in the sales history</span>
                <input
                  value={closedDates}
                  onChange={(event) => {
                    setClosedDates(event.target.value);
                    invalidateResult();
                  }}
                  placeholder="2025-01-01, 2025-04-18"
                />
                <small>Comma-separated dates using YYYY-MM-DD.</small>
              </label>
            </div>
            <label className="confirmation-box product-demand__confirmation">
              <input
                type="checkbox"
                checked={confirmNamesUnique}
                onChange={(event) => {
                  setConfirmNamesUnique(event.target.checked);
                  invalidateResult();
                }}
              />
              <span>
                <strong>Product names are unique and stable</strong>
                Use this fallback only when the CSV has no Product/SKU code.
              </span>
            </label>
          </details>

          <div className="section-actions section-actions--start">
            <button
              type="button"
              className="button"
              disabled={busy}
              onClick={() => void runProductDemand()}
            >
              {busy ? "Evaluating product history…" : "Evaluate product demand"}
            </button>
          </div>
        </div>
      )}

      {error ? <div className="notice notice--error" role="alert">{error}</div> : null}

      {result ? (
        <div className="product-demand__results" aria-live="polite">
          <div className="product-demand__summary">
            <div>
              <span>Preview forecasts</span>
              <strong>{result.preview_product_count.toLocaleString()}</strong>
            </div>
            <div>
              <span>Unavailable products</span>
              <strong>{result.unavailable_product_count.toLocaleString()}</strong>
            </div>
            <div>
              <span>Category fallbacks</span>
              <strong>{result.preview_category_count.toLocaleString()}</strong>
            </div>
            <div>
              <span>Required test weeks</span>
              <strong>{result.minimum_preview_test_weeks}</strong>
            </div>
          </div>

          <p className="product-demand__warning"><strong>Important:</strong> {result.warning}</p>

          {result.dataset_explanations.length > 0 ? (
            <div className="notice notice--warning">
              <strong>Dataset-level limitations</strong>
              <ul>
                {result.dataset_explanations.map((explanation) => (
                  <li key={explanation}>{explanation}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {result.category_dataset_explanations.length > 0 ? (
            <div className="notice notice--warning">
              <strong>Category fallback limitations</strong>
              <ul>
                {result.category_dataset_explanations.map((explanation) => (
                  <li key={explanation}>{explanation}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {previewProducts.length > 0 ? (
            <>
              <div className="product-demand__previews">
                {previewProducts.slice(0, visiblePreviews).map((product) => (
                  <ProductPreviewCard product={product} key={product.product_key} />
                ))}
              </div>
              {visiblePreviews < previewProducts.length ? (
                <button
                  type="button"
                  className="button button--secondary button--small"
                  onClick={() => setVisiblePreviews((count) => count + PRODUCT_PAGE_SIZE)}
                >
                  Show 20 more forecasts
                </button>
              ) : null}
            </>
          ) : (
            <div className="product-demand__empty">
              <h3>No product forecast passed the preview rules</h3>
              <p>
                {previewCategories.length > 0
                  ? "A broader category fallback passed and is shown below."
                  : "Open the unavailable-products section to see what must be corrected."}
              </p>
            </div>
          )}

          {previewCategories.length > 0 ? (
            <div className="product-demand__category-fallbacks">
              <div>
                <p className="eyebrow">Category fallback</p>
                <h3>Broader demand evidence</h3>
                <p>
                  These totals apply to the whole category and are not divided among products.
                </p>
              </div>
              <div className="product-demand__previews">
                {previewCategories.map((category) => (
                  <CategoryPreviewCard category={category} key={category.category_key} />
                ))}
              </div>
            </div>
          ) : null}

          {unavailableProducts.length > 0 ? (
            <details className="product-demand__unavailable">
              <summary>
                Review unavailable products ({unavailableProducts.length.toLocaleString()})
              </summary>
              <div className="product-demand__unavailable-list">
                {unavailableProducts.slice(0, visibleUnavailable).map((product) => (
                  <UnavailableProduct product={product} key={product.product_key} />
                ))}
              </div>
              {visibleUnavailable < unavailableProducts.length ? (
                <button
                  type="button"
                  className="button button--secondary button--small"
                  onClick={() => setVisibleUnavailable((count) => count + PRODUCT_PAGE_SIZE)}
                >
                  Show 20 more
                </button>
              ) : null}
            </details>
          ) : null}

          {unavailableCategories.length > 0 ? (
            <details className="product-demand__unavailable">
              <summary>
                Review unavailable category fallbacks ({unavailableCategories.length.toLocaleString()})
              </summary>
              <div className="product-demand__unavailable-list">
                {unavailableCategories.map((category) => (
                  <UnavailableCategory category={category} key={category.category_key} />
                ))}
              </div>
            </details>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function CategoryPreviewCard({ category }: { category: ProductDemandCategory }) {
  const forecast = category.forecast;
  if (forecast === null) return null;
  const unit = category.unit_of_measure ?? "units";
  return (
    <article className="product-demand-card product-demand-card--category">
      <div className="product-demand-card__head">
        <div>
          <p>Category-level forecast</p>
          <h3>{category.category_name}</h3>
          <small>{category.product_count.toLocaleString()} products combined</small>
        </div>
        <span className="quality-badge quality-badge--limited">Limited preview</span>
      </div>
      <div className="product-demand-card__numbers">
        <div>
          <span>Next 7 days</span>
          <strong>{formatUnits(forecast.total_units)} {unit}</strong>
        </div>
        <div>
          <span>Average daily planning rate</span>
          <strong>{formatUnits(forecast.average_daily_planning_rate)} {unit}</strong>
        </div>
      </div>
      <p><strong>Method:</strong> {category.selected_method_name}</p>
      {category.selection_reason ? (
        <p><strong>Why this method:</strong> {category.selection_reason}</p>
      ) : null}
      <p className="product-demand-card__warning">{category.warning}</p>
      <details className="product-demand-card__evidence">
        <summary>View category forecast evidence</summary>
        <dl>
          <div><dt>Historical test weeks</dt><dd>{category.evidence.shared_test_weeks}</dd></div>
          <div><dt>Beat zero benchmark</dt><dd>{category.evidence.benchmark_passed ? "Yes" : "No"}</dd></div>
          <div>
            <dt>Improvement over zero</dt>
            <dd>{category.evidence.skill_vs_zero_percent === null ? "Not available" : `${category.evidence.skill_vs_zero_percent.toFixed(1)}%`}</dd>
          </div>
        </dl>
      </details>
    </article>
  );
}

function UnavailableCategory({ category }: { category: ProductDemandCategory }) {
  return (
    <article>
      <div>
        <strong>{category.category_name}</strong>
        <small>{category.product_count.toLocaleString()} products</small>
      </div>
      <ul>
        {category.explanations.map((explanation) => <li key={explanation}>{explanation}</li>)}
      </ul>
    </article>
  );
}

function ProductPreviewCard({ product }: { product: ProductDemandProduct }) {
  const forecast = product.forecast;
  if (forecast === null) return null;
  const unit = product.unit_of_measure ?? "units";
  return (
    <article className="product-demand-card">
      <div className="product-demand-card__head">
        <div>
          <p>{product.product_name ?? "Unnamed product"}</p>
          <h3>{product.product_id ?? product.product_key}</h3>
        </div>
        <span className="quality-badge quality-badge--limited">Limited preview</span>
      </div>
      <div className="product-demand-card__numbers">
        <div>
          <span>Next 7 days</span>
          <strong>{formatUnits(forecast.total_units)} {unit}</strong>
        </div>
        <div>
          <span>Average daily planning rate</span>
          <strong>{formatUnits(forecast.average_daily_planning_rate)} {unit}</strong>
        </div>
      </div>
      <p className="product-demand-card__dates">
        {formatDate(forecast.forecast_dates[0])}–
        {formatDate(forecast.forecast_dates.at(-1) ?? forecast.forecast_dates[0])}
      </p>
      <p><strong>Method:</strong> {product.selected_method_name}</p>
      {product.selection_reason ? <p><strong>Why this method:</strong> {product.selection_reason}</p> : null}
      <p className="product-demand-card__warning">{product.warning}</p>
      <details className="product-demand-card__evidence">
        <summary>View forecast evidence</summary>
        <dl>
          <div><dt>Historical test weeks</dt><dd>{product.evidence.shared_test_weeks}</dd></div>
          <div><dt>Beat zero benchmark</dt><dd>{product.evidence.benchmark_passed ? "Yes" : "No"}</dd></div>
          <div>
            <dt>Improvement over zero</dt>
            <dd>{product.evidence.skill_vs_zero_percent === null ? "Not available" : `${product.evidence.skill_vs_zero_percent.toFixed(1)}%`}</dd>
          </div>
        </dl>
      </details>
    </article>
  );
}

function UnavailableProduct({ product }: { product: ProductDemandProduct }) {
  return (
    <article>
      <div>
        <strong>{product.product_name ?? product.product_id ?? product.product_key}</strong>
        {product.product_name && product.product_id ? <small>{product.product_id}</small> : null}
      </div>
      <ul>
        {product.explanations.map((explanation) => <li key={explanation}>{explanation}</li>)}
      </ul>
    </article>
  );
}

function parseDateList(value: string): string[] {
  if (!value.trim()) return [];
  return value
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(item) || Number.isNaN(Date.parse(`${item}T00:00:00Z`))) {
        throw new Error(`Closed date “${item}” must use YYYY-MM-DD.`);
      }
      return item;
    });
}

function formatUnits(value: number): string {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value);
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" })
    .format(new Date(`${value}T00:00:00`));
}

function messageFrom(error: unknown): string {
  return error instanceof Error ? error.message : "Product-demand evaluation failed.";
}
