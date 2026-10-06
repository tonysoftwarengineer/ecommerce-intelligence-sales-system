# Reference

Detailed reference for the Ecommerce Intelligence Sales System. The [README](../README.md) is the
overview; this page holds the full API, configuration, data rules, and evaluation history.

- [Architecture notes](#architecture-notes)
- [Setup notes](#setup-notes)
- [Roadmap status](#roadmap-status)
- [Supported data and first-release audience](#supported-data-and-first-release-audience)
- [Retail recognition contract](#retail-recognition-contract)
- [API](#api)
- [Data lifetime and isolation](#data-lifetime-and-isolation)
- [Configuration](#configuration)
- [Document search evaluation (RAG Phase 1)](#document-search-evaluation-rag-phase-1)
- [Document answers status (RAG Phase 2)](#document-answers-status-rag-phase-2)
- [Product-demand forecasting history](#product-demand-forecasting-history)
- [Tests](#tests)

## Architecture notes

The portfolio-level design, evidence, trade-offs, current limits, and future AI
boundary are documented in the
[architecture case study](ARCHITECTURE_CASE_STUDY.md). The accepted RAG
decision is recorded in
[ADR-005](architecture/ADR-005-rag-explanation-boundary.md). The account-free
portfolio boundary is recorded in
[ADR-013](architecture/ADR-013-portfolio-guest-session-rag-foundation.md).
[ADR-014](architecture/ADR-014-rag-phase-1-retrieval.md) records the
evaluated retrieval design. Guest isolation, atomic latest-version indexing,
MiniLM/Chroma retrieval, honest abstention, citations, and the dashboard evidence
panel are implemented. Experimental grounded document answers are implemented
behind claim-level citation and exact-quote checks; their locked Phase 2 release
evaluation is still pending.

```text
business CSV → preview → map → validate → quarantine/transform → analytics → dashboard
                                      ↘ eligible forecast previews and diagnostics
approved document → chunk/index latest version → retrieve evidence → verify cited AI claims or abstain
```

## Setup notes

`constraints.txt` locks every package, including transitive ones such as `torch`
and `numpy`, to the versions the test suite passed with. Install without it and
those libraries may resolve to newer, untested versions. Use
`pip install -r requirements.txt -c constraints.txt` alone only when reproducing
the production image, which never installs test/lint tooling (see `Dockerfile.api`).

The app does not download an external sales dataset at startup. The optional document embedding
model is preloaded in the demo image; local semantic retrieval may download its model on first use.

## Roadmap status

Built: retailer-focused REST API, generic CSV preview, schema
mapping, value validation, quarantine reporting, canonical transformation, generic analytics,
adaptive forecasting, retail status/discount/refund/payment rules, multi-currency reporting,
expiring analysis sessions, downloads, backend-owned data-quality readiness, guided CSV repair,
Preview Mode, and the guided React upload dashboard.

The ten-milestone trust and Diagnostic Intelligence roadmap is complete. See the
[roadmap](DIAGNOSTIC_INTELLIGENCE_ROADMAP.txt) and
[architecture case study](ARCHITECTURE_CASE_STUDY.md).

## Supported data and first-release audience

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

Use the [fictional retailer browser walkthrough](../tests/fixtures/retailer_demo/README.md)
for one coherent CSV and document example. The
[retailer evaluation matrix](evaluation/online_retailer_evidence_matrix.md)
separates exercised behavior from independent accuracy evidence.

## Retail recognition contract

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

## API

| Endpoint | Returns |
|---|---|
| `GET /api/v1/health` | Liveness check: `{"status": "ok"}` |
| `POST /api/v1/uploads/preview` | Temporary upload ID, expiry, CSV shape, types, and first 5 rows |
| `POST /api/v1/uploads/mapping-suggestions` | Explainable header-based mapping recommendations; the business must review them |
| `POST /api/v1/uploads/distinct-values` | Profile all distinct values for mapped status columns (capped at 100) |
| `POST /api/v1/uploads/validate-mapping` | Validate an upload's columns against the canonical sales schema |
| `POST /api/v1/uploads/validate-data` | Validate mapped values and return quarantine requirements |
| `POST /api/v1/uploads/transform` | Produce canonical sales data after required confirmation |
| `POST /api/v1/uploads/analyze` | Transform, analyze, forecast, and create a dashboard session |
| `GET /api/v1/observability/analysis-metrics` | Aggregate evaluation metrics when enabled and called with the admin token; otherwise 404 |
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
| `POST /api/v1/analyses/{analysis_id}/rag/answer-feedback` | Record a helpful / not helpful vote on an answer; stores only aggregate counts, no text |
| `GET /api/v1/observability/rag-answer-metrics` | Aggregate grounded-answer metrics when enabled and called with the admin token; otherwise 404 |

The API serves the retailer workflow without loading a benchmark sales dataset.

## Data lifetime and isolation

Business CSV uploads are held in process memory for at most 30 minutes and are removed early by the
web app after analysis succeeds. Derived analysis sessions and approved RAG source documents expire
after 2 hours. An HttpOnly anonymous guest cookie scopes uploads, analyses, and documents so another
browser session receives a not-found response. IDs are random, expired data is cleaned automatically,
and the stores support immediate deletion. These
process-local stores are suitable for the current single-server version; they are not shared between
multiple API instances and do not survive a server restart.
Cached document answers are removed when a supporting document is deleted or superseded. Periodic
cleanup removes answers whose sources have expired, along with expired cache entries.

## Configuration

All settings have working local defaults — deploying should never require editing source.
For local experimental grounded-answer development, copy `.env.example` to an
ignored `.env` and provide the key for the explicitly selected provider.
The example selects Groq with `openai/gpt-oss-20b`; Gemini remains selectable.
Environment variables supplied by a deployment always override values from that
local file.

| Variable | Default | Purpose |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `CORS_ORIGINS` | *(empty)* | Comma-separated exact origins for production, e.g. `https://dashboard.example.com` |
| `CORS_ORIGIN_REGEX` | any `localhost` port | Dev fallback, used only when `CORS_ORIGINS` is empty |
| `UPLOAD_TTL_MINUTES` | `30` | Fixed lifetime for temporary business CSV uploads |
| `UPLOAD_MAX_BYTES` | `10485760` | Maximum accepted CSV size in bytes (10 MiB) |
| `UPLOAD_RATE_LIMIT_PER_MINUTE` | `20` | CSV and RAG document upload attempts per anonymous guest per rolling minute |
| `ANALYSIS_TTL_MINUTES` | `120` | Lifetime of derived business-analysis sessions |
| `GUEST_SESSION_TTL_MINUTES` | `120` | Lifetime of an anonymous isolated portfolio-demo session |
| `GUEST_SESSION_COOKIE` | `ei_guest_session` | HttpOnly guest-session cookie name |
| `GUEST_COOKIE_SECURE` | `false` | Set `true` when the API is served over HTTPS |
| `RAG_DOCUMENT_TTL_MINUTES` | `120` | Lifetime of temporary approved RAG sources |
| `RAG_DOCUMENT_MAX_BYTES` | `2097152` | Maximum accepted RAG source size (2 MiB) |
| `GEMINI_API_KEY` | empty | Server-only Gemini credential; answers are unavailable when absent |
| `GROQ_API_KEY` | empty | Server-only Groq credential; required when `RAG_ANSWER_PROVIDER=groq` |
| `RAG_ANSWER_MODEL` | `gemini-3.8-flash` | Model for the explicitly selected experimental answer provider |
| `RAG_ANSWER_TIMEOUT_SECONDS` | `5.0` | Provider request timeout |
| `RAG_ANSWER_PROVIDER` | `gemini` | `gemini`, `groq`, or `fake`; use `fake` only for deterministic CI/browser tests |
| `RAG_ANSWER_MAX_OUTPUT_TOKENS` | `1024` | Hard maximum generated tokens for one grounded answer |
| `RAG_ANSWER_RATE_LIMIT_PER_MINUTE` | `6` | Provider-backed answer attempts per anonymous guest per rolling minute |
| `RAG_ANSWER_DAILY_BUDGET` | `100` | Provider-backed answers per UTC day across all visitors; repeated identical questions are served from a cache and do not count |
| `DEVELOPMENT_OBSERVABILITY_ENABLED` | `false` | Enable the two aggregate metrics endpoints; requires `DEVELOPMENT_OBSERVABILITY_TOKEN` or the API refuses to start |
| `DEVELOPMENT_OBSERVABILITY_TOKEN` | empty | Shared admin secret; callers send `Authorization: Bearer <token>`. A missing or wrong token returns 404 |

## Document search evaluation (RAG Phase 1)

The frozen semantic configuration uses `all-MiniLM-L6-v2`, 224-token chunks,
32-token overlap, and a 0.40 cosine-similarity gate. On the untouched 20-case
locked test it reached 93.75% Top-1 source accuracy, 94.12% Top-3 source recall,
100% unsupported-question abstention, and 8.482 ms warm p95 latency. The full
reports are in [`docs/evaluation/rag_phase_1`](evaluation/rag_phase_1).

```bash
# Tune only against the development split.
python -m scripts.evaluate_rag_retrieval --backend chroma --split development --select-development

# Run a frozen configuration against the locked split once.
python -m scripts.evaluate_rag_retrieval --backend chroma --split locked_test \
  --config docs/evaluation/rag_phase_1/chroma_frozen_config.json

# Run during a future deployed-image build so runtime does not download a model.
python -m scripts.preload_rag_model

# The provided API image performs that preload during its build.
docker build -f Dockerfile.api -t ecommerce-intelligence-api .
```

## Document answers status (RAG Phase 2)

Grounded document answers are implemented as an experimental layer over the
frozen Phase 1 retriever. Documents are isolated by guest and analysis. Every
returned claim must cite a retrieved chunk and include an exact quote that the
API verifies before returning the response. Missing credentials, provider
failures, invalid model output, and unsupported questions return no generated
claims; the analytics dashboard remains operational.

The deterministic fake-provider development run validates the wiring,
verification, abstention, isolation, and latency paths. It intentionally does
not count as a real-provider quality evaluation and did not pass the gold-claim
coverage gate. The untouched locked Phase 2 run and manual failure review remain
pending, so the feature stays labelled experimental. See
[`ADR-015`](architecture/ADR-015-experimental-grounded-document-answers.md)
and the [development report](evaluation/rag_phase2_development_fake.md).

The separate `hard-development` suite contains eight longer synthetic documents
for one fictional retailer and twenty adversarial development questions. It is
for answer-quality repair only: its detailed per-case trace is written under
ignored `data/private/`, and it never changes the frozen Phase 1 corpus or the
untouched Phase 2 locked set.

The recorded real Gemini hard-development run had 18 provider-unavailable cases
(`gemini_http_429`) and no supported-case provider responses. It is inconclusive
about answer quality, and the feature remains experimental. See the
[hard-development report](evaluation/rag_phase2_hard_development.md).

The first Groq hard-development run returned seven verified answers and passed
unsupported-question abstention, isolation, and latency checks. It was still
inconclusive: eleven supported cases were unavailable (ten `groq_http_429` and
one `groq_http_400`), leaving 28.6% gold-claim coverage. No retrieval or answer
policy was tuned after this run. See the separate
[Groq hard-development report](evaluation/rag_phase2_groq_hard_development.md).

Two later Groq development runs on 2026-09-27 were also inconclusive. A paced
run returned 15 answers with 57.1% reference coverage but three provider
failures ([report](evaluation/rag_phase2_groq_hard_development_2026-09-27.md)).
A rerun with repaired diagnostics returned eight answers and ten provider
failures (nine transport errors, one HTTP 400), with 28.6% full-suite coverage
([report](evaluation/rag_phase2_groq_hard_development_diagnostics_rerun_2026-09-27.md)).
Every returned answer passed exact-quote verification, unsupported questions were
always declined, and no document crossed a scope boundary. These are
provider-availability results, not evidence of reliable answer quality.

```bash
# Development-only: emits a private trace and a sanitized summary.
python -m scripts.evaluate_rag_answers --suite hard-development --split development
```

## Product-demand forecasting history

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

## Tests

```bash
pytest -q
```

The backend suite tests the retailer workflow without downloading Olist data.

`tests/test_csv_trust_matrix.py` runs 15 end-to-end CSV scenarios through the upload API. The
matrix covers all revenue modes, discount scopes, statuses, refunds, duplicate and malformed rows,
header suggestions, date formats, missing periods, forecasting eligibility, and currency isolation.

The Playwright suite tests the browser-to-API-to-dashboard journey in Chromium. Install its browser
once, then run the browser journeys:

```bash
cd frontend
npx playwright install chromium
npm run test:e2e
```

The suite starts isolated API and frontend servers (it never reuses one already running unless
`E2E_REUSE_SERVER=1`). Its journeys cover a complete evidence-rich analysis, status values that
are still loading versus failed, required quarantine confirmation, honest unavailable states for
limited data, product-demand previews and the category fallback, discount rules cleared when a
replacement CSV lacks them, the fictional retailer from upload to document answers, and the
dashboard's section sidebar and keyboard-only phone menu. Failure screenshots, traces, and
screen recordings are written to ignored local test artifact directories. Use
`npm run test:e2e:report` to inspect the HTML report.
