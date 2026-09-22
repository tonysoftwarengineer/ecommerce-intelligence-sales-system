# Ecommerce Intelligence Sales System

A portfolio MVP for small online retailers selling physical products with repeat
sales. A retailer uploads an order export, reviews column meanings and sales
rules, and receives validated sales analytics, evidence-backed diagnostics,
forecast previews when eligible, and experimental answers from approved
documents. Other valid sales CSVs can use the same mapping path; the business
focus is not an upload restriction.

The [Olist Brazilian E-Commerce dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
(2016–2018) powers a separate fixed demo and benchmark. Its dashboard uses
Brazilian Real (`R$`). Olist-specific fields are not the uploaded-business contract.

![Dashboard](docs/dashboard.png)

## What it does

**Olist fixed-demo analytics** — total revenue, revenue by month, average order value, top categories, top customers, revenue by state.

**Olist benchmark machine learning**
- *Revenue forecasting* — a linear trend fit over a recent window. The window size was chosen by sweeping candidates against a rolling backtest, not assumed: 6 months scored **14.2% MAPE** vs 26.0% for 12 months and 31.1% for full history.
- *Customer segmentation* — RFM features + k-means over 94,398 customers, labelled from cluster centroids after fitting. The segmentation surfaces a real finding: **High Value is the only segment that orders more than once** (2.11 avg orders vs 1.00 everywhere else).

**Olist data checks** — joins validate key uniqueness and row counts rather than silently producing wrong numbers; canceled and unfulfilled orders are excluded from revenue; customer-level analysis keys on `customer_unique_id` (a per-person id) rather than `customer_id` (a per-order token).

**Analyze your business** — uploaded business CSVs can be previewed with direct identifiers masked,
given explainable mapping suggestions, value-validated, quarantined with user confirmation, and
transformed into a canonical sales dataset. The product
then calculates capability-aware KPIs and charts, evaluates transparent forecast candidates with
rolling backtests, and provides canonical and quarantine downloads. Supported revenue modes are
row total, unit price × quantity, and order total.

### First-release audience and questions

The intended user is the owner or operator of a small online shop selling
repeat-purchase physical products. Their first job is to understand validated
sales changes: recognized revenue, orders, average order value, supported
category or region contributors, data limitations, and what to investigate.
Approved shipping, refund, or catalogue documents can be searched for cited
evidence; they do not change sales calculations. Seven-day product-unit demand
remains an optional **Preview — not decision-ready** feature, not a restocking
instruction.

The current sales analysis requires a mapped order ID, order date, customer ID,
and a valid revenue representation (row total, price × quantity, or order total).
If the export has no order status, the business must confirm every row is a
completed sale. Product demand additionally needs a stable SKU or confirmed
unique product name, quantity, unit of measure, sufficient safe calendar history,
and truthful open-day and stockout confirmations. Category fallback needs a
mapped, confirmed category and compatible units. Missing or ambiguous evidence
reduces capability or returns an unavailable result; it is never invented.

Use the [fictional retailer browser walkthrough](tests/fixtures/retailer_demo/README.md)
for one coherent CSV and document example. The
[retailer evaluation matrix](docs/evaluation/online_retailer_evidence_matrix.md)
separates exercised behavior from independent accuracy evidence.

## Architecture

The portfolio-level design, evidence, trade-offs, current limits, and future AI
boundary are documented in the
[architecture case study](docs/ARCHITECTURE_CASE_STUDY.md). The accepted RAG
decision is recorded in
[ADR-005](docs/architecture/ADR-005-rag-explanation-boundary.md). The account-free
portfolio boundary is recorded in
[ADR-013](docs/architecture/ADR-013-portfolio-guest-session-rag-foundation.md).
[ADR-014](docs/architecture/ADR-014-rag-phase-1-retrieval.md) records the
evaluated retrieval design. Guest isolation, atomic latest-version indexing,
MiniLM/Chroma retrieval, honest abstention, citations, and the dashboard evidence
panel are implemented. Experimental grounded document answers are implemented
behind claim-level citation and exact-quote checks; their locked Phase 2 release
evaluation is still pending.

```
ingest() → clean_all() → join_all() → run_analysis() → report / dashboard / API
                              ↓
                    forecast + segmentation

business CSV → preview → map → validate → quarantine/transform → analyze → dashboard

approved document → chunk/index latest version → retrieve evidence → verify cited AI claims or abstain
```

| Module | Responsibility |
|---|---|
| `config.py` | Paths, dataset id, table filenames — single source of truth |
| `src/ingest.py` | Downloads via `kagglehub` (skipped if `data/` is populated) and loads the raw CSVs |
| `src/stages/clean.py` | Per-table cleaning — dates, order-status filtering, missing values |
| `src/stages/join.py` | Merges into one analysis-ready frame, with join validation |
| `src/stages/analyze.py` | The six business-question functions |
| `src/stages/report.py` | Console formatting — currency, state names, category labels |
| `src/stages/visualize.py` | Matplotlib dashboard (2×2 grid) |
| `src/models/forecast.py` | Trend forecast, rolling backtest, MAE/RMSE/MAPE metrics |
| `src/models/segmentation.py` | RFM + k-means, centroid-based labelling |
| `src/schema_mapping.py` | Canonical CSV field definitions and schema-mapping validation |
| `src/generic_sales/` | Validation, canonical transformation, generic analytics, and adaptive forecasting |
| `src/product_demand/` | Product/category readiness, calendar semantics, rolling evaluation, candidate selection, and preview trust policy |
| `src/rag/` | Chunking, lexical/semantic indexes, retrieval policy, metrics, and untrusted-context contracts |
| `src/pipeline.py` | `build_dataset()` and `run_pipeline()` |
| `api/` | FastAPI app — routes, serializers, expiring upload and analysis-session storage |
| `frontend/` | React + TypeScript + Recharts dashboard |

## Setup

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

No Kaggle credentials are needed — Olist is a public dataset and `kagglehub` fetches it anonymously on first run (~43MB). `data/` is gitignored and populated automatically.

## Usage

**Console report**

```bash
python3 -m main
```

**Matplotlib dashboard**

```bash
python3 -m src.stages.visualize
```

**Web dashboard** — two terminals, from the project root:

```bash
# 1. API (wait for "Startup complete" — it builds the dataset once, ~5s)
python3 -m uvicorn api.main:app --host 127.0.0.1 --port 8000

# 2. Frontend
cd frontend && npm install && npm run dev -- --host 127.0.0.1
```

Then open <http://127.0.0.1:5173>. Interactive API docs are at <http://127.0.0.1:8000/docs>.

The frontend automatically follows the hostname in the browser address bar for
local API calls. You can also use `localhost` for both services, but do not mix
`localhost` and `127.0.0.1` in the same local session because guest uploads are
protected by host-scoped cookies.

## API

| Endpoint | Returns |
|---|---|
| `GET /api/v1/health` | Readiness of each cached subsystem |
| `GET /api/v1/report` | All six analytics metrics |
| `GET /api/v1/forecast` | 3-month revenue projection |
| `GET /api/v1/segments` | Per-segment summary (counts + mean RFM) |
| `POST /api/v1/uploads/preview` | Temporary upload ID, expiry, CSV shape, types, and first 5 rows |
| `POST /api/v1/uploads/mapping-suggestions` | Explainable header-based mapping recommendations; the business must review them |
| `POST /api/v1/uploads/distinct-values` | Profile all distinct values for mapped status columns (capped at 100) |
| `POST /api/v1/uploads/validate-mapping` | Validate an upload's columns against the canonical sales schema |
| `POST /api/v1/uploads/validate-data` | Validate mapped values and return quarantine requirements |
| `POST /api/v1/uploads/transform` | Produce canonical sales data after required confirmation |
| `POST /api/v1/uploads/analyze` | Transform, analyze, forecast, and create a dashboard session |
| `GET /api/v1/observability/analysis-metrics` | Process-local, privacy-safe evaluation metrics for completed analyses |
| `DELETE /api/v1/uploads/{upload_id}` | Immediately remove a temporary upload |
| `GET /api/v1/analyses/{analysis_id}` | Restore a generic business analysis session |
| `POST /api/v1/analyses/{analysis_id}/product-demand` | Opt-in, evidence-gated seven-day fulfilled-unit previews by product, with guarded category fallback |
| `GET /api/v1/analyses/{analysis_id}/canonical.csv` | Download accepted canonical rows |
| `GET /api/v1/analyses/{analysis_id}/quarantine.csv` | Download rejected rows and reasons |
| `DELETE /api/v1/analyses/{analysis_id}` | Immediately remove an analysis session |
| `POST /api/v1/analyses/{analysis_id}/rag/documents` | Atomically store, chunk, and index an approved UTF-8 text/Markdown source for one analysis |
| `GET /api/v1/analyses/{analysis_id}/rag/documents` | List source metadata for the owned analysis |
| `DELETE /api/v1/analyses/{analysis_id}/rag/documents/{document_id}` | Remove one analysis-scoped RAG source |
| `POST /api/v1/analyses/{analysis_id}/rag/retrieve` | Return up to three cited evidence excerpts or an honest abstention; no generated answer |
| `POST /api/v1/analyses/{analysis_id}/rag/answer` | Return only verified, claim-level grounded answers or a bounded abstention/unavailable result |

`/api/v1/segments` returns a summary by default. Pass `?include_customers=true` for the full per-customer rows — that response is ~12MB versus ~500 bytes, so it's opt-in.

The dataset is built once during app startup and cached in memory; requests are served from that cache. Forecasting and segmentation are isolated — if either fails, its endpoint returns 503 while the rest of the API keeps working, and the failure is logged with a full traceback.

Business CSV uploads are held in process memory for at most 30 minutes and are removed early by the
web app after analysis succeeds. Derived analysis sessions and approved RAG source documents expire
after 2 hours. An HttpOnly anonymous guest cookie scopes uploads, analyses, and documents so another
browser session receives a not-found response. IDs are random, expired data is cleaned automatically,
and the stores support immediate deletion. These
process-local stores are suitable for the current single-server version; they are not shared between
multiple API instances and do not survive a server restart.

### RAG Phase 1 evaluation

The frozen semantic configuration uses `all-MiniLM-L6-v2`, 224-token chunks,
32-token overlap, and a 0.40 cosine-similarity gate. On the untouched 20-case
locked test it reached 93.75% Top-1 source accuracy, 94.12% Top-3 source recall,
100% unsupported-question abstention, and 8.482 ms warm p95 latency. The full
reports are in [`docs/evaluation/rag_phase_1`](docs/evaluation/rag_phase_1).

```bash
# Tune only against the development split.
python3 -m scripts.evaluate_rag_retrieval --backend chroma --split development --select-development

# Run a frozen configuration against the locked split once.
python3 -m scripts.evaluate_rag_retrieval --backend chroma --split locked_test \
  --config docs/evaluation/rag_phase_1/chroma_frozen_config.json

# Run during a future deployed-image build so runtime does not download a model.
python3 -m scripts.preload_rag_model

# The provided API image performs that preload during its build.
docker build -f Dockerfile.api -t ecommerce-intelligence-api .
```

### RAG Phase 2 status

Grounded document answers are implemented as an experimental layer over the
frozen Phase 1 retriever. Documents are isolated by guest and analysis. Every
returned claim must cite a retrieved chunk and include an exact quote that the
API verifies before returning the response. Missing credentials, provider
failures, invalid model output, and unsupported questions return no generated
claims; the analytics dashboard remains operational.

The deterministic fake-provider development run validates the wiring,
verification, abstention, isolation, and latency paths. It intentionally does
not count as a Gemini quality evaluation and did not pass the gold-claim
coverage gate. The untouched locked Phase 2 run and manual failure review remain
pending, so the feature stays labelled experimental. See
[`ADR-015`](docs/architecture/ADR-015-experimental-grounded-document-answers.md)
and the [development report](docs/evaluation/rag_phase2_development_fake.md).

The separate `hard-development` suite contains eight longer synthetic documents
for one fictional retailer and twenty adversarial development questions. It is
for answer-quality repair only: its detailed per-case trace is written under
ignored `data/private/`, and it never changes the frozen Phase 1 corpus or the
untouched Phase 2 locked set.

The recorded real Gemini hard-development run had 18 provider-unavailable cases
(`gemini_http_429`) and no supported-case provider responses. It is inconclusive
about answer quality, and the feature remains experimental. See the
[hard-development report](docs/evaluation/rag_phase2_hard_development.md).

```bash
# Development-only: emits a private trace and a sanitized summary.
python3 -m scripts.evaluate_rag_answers --suite hard-development --split development
```

### Retail recognition contract

The generic dashboard is operational sales intelligence, not certified accounting software. It
requires the business to confirm the meaning of its data before calculations:

- Completed orders are recognized as sales. Pending orders are shown separately, cancelled orders
  are excluded, and returns preserve the original sale plus a separate refund.
- Unknown order or payment statuses are quarantined until the business classifies them. If no order
  status exists, the business must explicitly confirm that every row is completed.
- Discounts support fixed or percentage values at per-unit, per-line, or entire-order scope.
  Entire-order discounts may remain unallocated or be distributed proportionally across line items.
- Reported totals and calculated price × quantity totals are preserved together. The selected
  revenue authority wins; differences can warn or quarantine according to the confirmed policy.
- Tax, shipping, pending value, refunds, disputes, and chargebacks remain separate from recognized
  revenue. Distinct currencies are analyzed independently and are never added together.
- If both tax and a refund amount are mapped, the business must confirm whether refunds include tax;
  the system never guesses that accounting treatment. Cash collection is unavailable unless a
  payment-amount column is mapped—payment status alone does not prove cash received.
- Refund-only periods remain visible in revenue reporting but are excluded from forecast history,
  so post-sale adjustments do not distort demand forecasting.
- Invalid and conflicting rows are never silently repaired. They are quarantined with machine-readable
  issue codes and human-readable reasons for download and review.

## Configuration

All settings have working local defaults — deploying should never require editing source.
For local Gemini development only, copy `.env.example` to an ignored `.env` and
provide `GEMINI_API_KEY`. Environment variables supplied by a deployment always
override values from that local file.

| Variable | Default | Purpose |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `DATA_DIR` | `./data` | Where the CSVs are stored |
| `KAGGLE_DATASET` | `olistbr/brazilian-ecommerce` | Dataset to download |
| `CORS_ORIGINS` | *(empty)* | Comma-separated exact origins for production, e.g. `https://dashboard.example.com` |
| `CORS_ORIGIN_REGEX` | any `localhost` port | Dev fallback, used only when `CORS_ORIGINS` is empty |
| `UPLOAD_TTL_MINUTES` | `30` | Fixed lifetime for temporary business CSV uploads |
| `UPLOAD_MAX_BYTES` | `10485760` | Maximum accepted CSV size in bytes (10 MiB) |
| `ANALYSIS_TTL_MINUTES` | `120` | Lifetime of derived business-analysis sessions |
| `GUEST_SESSION_TTL_MINUTES` | `120` | Lifetime of an anonymous isolated portfolio-demo session |
| `GUEST_SESSION_COOKIE` | `ei_guest_session` | HttpOnly guest-session cookie name |
| `GUEST_COOKIE_SECURE` | `false` | Set `true` when the API is served over HTTPS |
| `RAG_DOCUMENT_TTL_MINUTES` | `120` | Lifetime of temporary approved RAG sources |
| `RAG_DOCUMENT_MAX_BYTES` | `2097152` | Maximum accepted RAG source size (2 MiB) |
| `GEMINI_API_KEY` | empty | Server-only Gemini credential; answers are unavailable when absent |
| `RAG_ANSWER_MODEL` | `gemini-3.8-flash` | Configurable Gemini model for experimental grounded answers |
| `RAG_ANSWER_TIMEOUT_SECONDS` | `5.0` | Provider request timeout |
| `RAG_ANSWER_PROVIDER` | `gemini` | Use `fake` only for deterministic CI/browser tests |

## Tests

```bash
pytest -q
```

Tests marked `integration` build the real dataset rather than mocking it, so their first run
downloads the data. The generic CSV and analytics tests do not need the Olist dataset.

`tests/test_csv_trust_matrix.py` runs 15 end-to-end CSV scenarios through the upload API. The
matrix covers all revenue modes, discount scopes, statuses, refunds, duplicate and malformed rows,
header suggestions, date formats, missing periods, forecasting eligibility, and currency isolation.

The Playwright suite tests the browser-to-API-to-dashboard journey in Chromium. Install its browser
once, then run the four focused flows:

```bash
cd frontend
npx playwright install chromium
npm run test:e2e
```

The suite starts isolated API and frontend servers when they are not already running. It covers a
complete evidence-rich analysis, required quarantine confirmation, friendly unavailable states for
limited data, and the product-demand upload-to-preview journey. Failure screenshots, traces, and
screen recordings are written to ignored local test artifact directories. Use
`npm run test:e2e:report` to inspect the HTML report.

## Project structure

```
config.py
main.py
api/            FastAPI backend
src/
├── ingest.py
├── pipeline.py
├── logging_config.py
├── models/     forecast.py, segmentation.py
└── stages/     clean.py, join.py, analyze.py, report.py, visualize.py
frontend/       React + TypeScript dashboard
tests/
```

## Roadmap

Built: Olist analytics, charts, forecasting + segmentation, REST API, generic CSV preview, schema
mapping, value validation, quarantine reporting, canonical transformation, generic analytics,
adaptive forecasting, retail status/discount/refund/payment rules, multi-currency reporting,
expiring analysis sessions, downloads, backend-owned data-quality readiness, guided CSV repair,
Preview Mode, and the guided React upload dashboard.

The ten-milestone trust and Diagnostic Intelligence roadmap is complete. See the
[roadmap](docs/DIAGNOSTIC_INTELLIGENCE_ROADMAP.txt) and
[architecture case study](docs/ARCHITECTURE_CASE_STUDY.md).

The primary product-demand target is now defined as a per-product seven-day
fulfilled-unit total. Its evaluation engine compares transparent weekly methods,
including SBA/Croston for intermittent demand, against a zero benchmark. Accepted
ADR-010 permits only unavailable or strongly labelled limited-preview states;
date-specific and supported forecasts remain unapproved.

The accepted product-demand policy is now connected through a tested opt-in API
and dashboard journey without changing the existing revenue forecast. Eligible
products show only a strongly labelled seven-day limited preview; unavailable
products retain correction reasons. When every product in a confirmed category
is too intermittent, a guarded fallback may show only the combined category
total. It never allocates that number back to products or shows unreconciled
product and category forecasts together. A disjoint-product, thirteen-week M5
locked holdout passed for delayed-start, dense, and intermittent demand but
failed the predeclared sparse-demand gate. Supported use therefore remains
unapproved. A simple sparse-abstention candidate then failed a fresh holdout,
and a three-block consistency rule failed development screening; neither changed
the live policy. The next forecast checkpoint needs independent retailer data
and clearer stockout and lifecycle evidence, not further tuning on those scored
cohorts. RAG Phase 1 retrieval is evaluated and Phase 2 document answers are
experimental. Real-business validation, authenticated durable storage, tenant
boundaries, protected monitoring, and deployment remain later production
foundations.

## Data & license

Dataset: ["Brazilian E-Commerce Public Dataset by Olist"](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) on Kaggle. See the Kaggle page for license terms.

## Development

```bash
ruff check .              # lint
ruff format .             # format
mypy .                    # type check
pytest -q                 # all tests
pytest -q -m "not integration"   # unit tests only (~2s, no data needed)
```

Tests marked `integration` build the real dataset, so they're slower and need network on first run. CI runs the unit subset plus lint, format, types, and a frontend typecheck/build.
