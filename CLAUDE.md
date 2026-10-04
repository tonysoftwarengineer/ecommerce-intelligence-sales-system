# Shared AI Handoff

This is the rolling current-state snapshot for both Codex and Claude Code. Read
[`AGENTS.md`](AGENTS.md) first: it is the authoritative stable engineering contract. This file
records what is currently true so the next tool can orient itself quickly without reconstructing
the project from chat history.

## Working Agreement

- Read `AGENTS.md`, then this file, before acting.
- Inspect `git status --short` and recent Git history before editing. Preserve work you did not
  create.
- Use one active editor at a time. Do not make overlapping changes while another coding tool is
  working in the repository.
- Update this snapshot after a completed implementation, evaluation, review, or user-approved
  design decision. Do not update it for individual shell commands or work still in progress.
- Never place secrets, `.env` contents, private CSV rows, customer identifiers, product-level
  private results, or private evaluation traces in this file.

## Snapshot Format

When updating, keep these headings and replace only the factual content beneath them:

1. Updater and date
2. Completed phase
3. Changed areas
4. Verification
5. Current limitations
6. Next recommended work
7. Decisions requiring the user

## Current Snapshot

### Updater and date

Claude Code — 2026-10-04 (Stage B reviewed; dashboard UI redesign complete and CI verified)

### Completed phase

The committed portfolio MVP now includes the generic sales workflow, diagnostics, bounded
product-demand previews, RAG evidence retrieval, experimental grounded document answers, API,
frontend, browser coverage, and deployment scaffolding. The most recent completed research phase
was the DataCo public-data product-forecast coverage diagnosis.

The repository is now on GitHub (public: `tonysoftwarengineer/ecommerce-intelligence-sales-system`,
remote `origin`, branch `main`). The CI coverage gaps from the architecture review are closed and
proven on GitHub's runners: `.github/workflows/ci.yml` runs the Playwright browser suite and a
production-image build as their own jobs, and runs `pip-audit` / `npm audit` as report-only steps.

A focused dependency security pass updated the frontend's transitive `nanoid` lockfile entry and
recorded the remaining Python findings in the
[dependency security triage](docs/evaluation/dependency_security_triage.md).

The experimental Phase 2 answer layer now also supports an explicit Groq REST
provider using `openai/gpt-oss-20b`. It uses the same retrieved-excerpt-only
prompt boundary and deterministic exact-quote verifier as Gemini; no automatic
fallback was added.

RAG operational controls now cap generated answers at 1,024 tokens, limit each
anonymous guest to six provider-backed answer requests per rolling minute, and
expose privacy-safe process-local aggregate usage/latency metrics at
`/api/v1/observability/rag-answer-metrics`. Unsupported questions consume no
provider budget. There is no automatic retry, provider fallback, or retriever
fallback.

The two observability endpoints are now disabled by default and return `404`
unless a local developer explicitly sets `DEVELOPMENT_OBSERVABILITY_ENABLED=true`.
Claude Code's committed token guard also requires `DEVELOPMENT_OBSERVABILITY_TOKEN`
and a matching Bearer token on requests. The ignored local `.env` now disables
observability, so no token is needed for ordinary app startup or tests.
Provider configuration failures do not consume a guest's answer allowance,
verifier-rejected provider responses retain aggregate token usage, and stale
answers are cleared before each new dashboard request.

A fresh, paced Groq hard-development run was recorded separately on 2026-09-27.
It did not run the locked set or tune any policy.

The completed development-diagnostics repair now records actual provider payloads,
verified claims, per-reference evidence availability, and separate pacing delays.
It preserves scoring, release thresholds, retrieval, prompts, and production behavior.
See the [offline diagnostics review](docs/evaluation/rag_phase2_diagnostics_review.md).

One fresh complete Groq hard-development run used the repaired diagnostics and
30-second pacing. Its manual review is complete; no code or policy was changed.
It remains inconclusive because of transport failures and an undiagnosed HTTP 400.
See the [diagnostic rerun report](docs/evaluation/rag_phase2_groq_hard_development_diagnostics_rerun_2026-09-27.md).

Phase 1 pre-deploy hardening is complete (commits 412f3c1, 99844a7): the API image runs as a
non-root user with a health check, test/lint tooling is out of the production image, and CSV and
RAG document uploads are rate-limited per anonymous guest.

The Python runtime upgrade is complete ([ADR-016](docs/architecture/ADR-016-python-3-12-runtime-and-dependency-lock.md);
commits 0676dda, 315bd5d): Python 3.12 everywhere, an initial `constraints.txt` lock of 120 packages
used by Docker, CI, and `pip-audit`, CPU-only `torch`, and FastAPI 0.141.1 / Starlette 1.7.0.
Known Python vulnerabilities fell from 57 to 11 at the time of that upgrade. CI now also builds and smoke-tests the
production image (commit 327a0d0). All pre-deploy hardening is done.

Phase 2 Stage A is complete (commit da4f757; built by Codex, finished by Claude Code). The landing
page offers "Try a sample retailer", which loads `frontend/public/demo/retailer_sales.csv` (a
clearly fictional shop, "Harbor Home") into the same upload -> mapping -> validation -> dashboard
flow as a real upload; the user chose this guided path over a direct-to-dashboard shortcut. The
API no longer downloads the Olist dataset at startup or serves `/report`, `/forecast`,
`/segments`; `/health` returns `{"status": "ok"}`.

Phase 2 Stage B is complete (commit 90dfbfb;
[ADR-017](docs/architecture/ADR-017-retire-olist-demo.md)). The unused Olist console entry,
pipeline, models, API response types, and frontend view were removed, as were
`kagglehub` and `matplotlib`. The live CSV serializers, shared charts, `scikit-learn` for
TF-IDF, and `openpyxl` for offline evaluations remain. The generic product, forecast trust
policy, and RAG behavior did not change. `constraints.txt` was regenerated from a fresh
Python 3.12 environment after its full suite passed; it now pins 113 packages.

Claude Code reviewed Stage B against its brief (every claim checked with git, gh, and grep): it
followed the brief, kept out of the frontend files reserved for the redesign, and its recorded
numbers match CI. Deleting the root `main.py` went beyond the brief and was correct (it imported
only the deleted pipeline). Three comment slips were fixed in b94d996: the `constraints.txt`
rebuild recipe now installs CPU-only `torch` like CI and Docker, and two stale comments.

The dashboard UI redesign is complete (c6b680d; user-approved design). One page with a jump-link
sidebar (Overview: Data check, Key numbers; Sales: Revenue trend, Categories and regions,
Customers and revenue math; Insights: What changed, Revenue estimate, Product demand; Documents),
which becomes a "Sections" menu below 1024 px. Every CSS font size uses one scale in `index.css`
(`--text-xs` 12 px floor to `--text-xl` 32 px); `--text-muted` is 56% white (about 6:1, was 38%,
about 3.5:1). Key numbers show four cards plus three chips. The dashboard now opens at its top
(it used to keep the setup page's scroll position, landing visitors near the bottom). Unused
Olist CSS and colour tokens were removed. The setup wizard and landing page gained the larger
type scale but kept their layout.

Pre-testing hardening is complete (user-approved order; commits dec59bb, a9750c8, 80ef5d9):
- AI answer quota: an app-wide daily budget (`RAG_ANSWER_DAILY_BUDGET`, default 100 per UTC day)
  plus a verified-answer cache (`api/rag_answer_cache.py`). See ADR-015 for the key design: chunk
  IDs embed per-upload document IDs, so the key replaces them with positions; cached answers are
  remapped and re-verified. No automatic provider fallback (user decision).
- CSV parsing and document indexing run in worker threads (`run_in_threadpool`) so one upload no
  longer blocks the event loop for every visitor.
- Tester feedback: a "Give feedback" footer link to `.github/ISSUE_TEMPLATE/feedback.yml` (public;
  warns against private data) and per-answer Helpful / Not helpful votes counted in the
  content-free answer metrics.

### Changed areas

- The generic business workflow remains: CSV upload, explicit mapping, validation and quarantine,
  canonical transformation, analytics, diagnostics, and capability-gated dashboard features.
- Olist-only code and the root `main.py` console entry are retired. The live entry point remains
  `api.main:app`. Historical Olist research results remain in the README, labelled as history.
- Product demand remains a seven-day, units-only planning preview. The DataCo audit investigated
  low coverage without changing its methods, eligibility rules, API, or dashboard trust gate.
- RAG Phase 1 retrieval is frozen and independently usable. Phase 2 adds claim-level grounded
  answers with exact support quotes and deterministic citation verification. Gemini and Groq are
  explicit selectable providers, but Phase 2 remains experimental.
- Deployment and portfolio documentation are committed. Use the linked reports for detailed
  findings rather than copying evidence into this snapshot.
- CI (`.github/workflows/ci.yml`) has four jobs, all on Python 3.12 with `-c constraints.txt`
  and CPU-only `torch`: `backend` (lint, format check, mypy, full pytest, `pip-audit` of
  `constraints.txt`), `frontend`
  (tsc, `npm run lint`, build, `npm audit`), `e2e` (needs `backend` + `frontend`; Playwright
  against the fake RAG provider and tfidf retrieval backend, no real key needed), and `docker`
  (needs `backend`; builds `Dockerfile.api`, waits for `/api/v1/health`, fails if it runs as root).
- Quality-gate fixes: all 15 files that failed `ruff format --check` were reformatted (cosmetic
  only); `scripts/__init__.py` was added so mypy resolves `scripts.<name>` once; mypy now excludes
  `tests/` (`pyproject.toml`, `exclude = ["^tests/"]`) because 59 pre-existing errors were all
  loosely typed JSON fixtures in tests, none in `src/`, `api/`, or `scripts/`; and
  `pythonpath = ["."]` was added to pytest config because bare `pytest` (the documented command)
  could not import `src`/`api`/`scripts` on CI.
- `frontend/package-lock.json` now resolves `nanoid` 3.3.19 instead of 3.3.16; no application code,
  backend requirement, or CI audit policy changed.
- RAG evaluation unwraps `ProviderGeneration` only for private tracing and retains
  verified claims separately. Diagnostics distinguish empty retrieval, missing
  reference evidence, outages, verifier rejections, and answer/reference mismatches.
  Supplemental provider-available coverage never replaces full-suite coverage.
  The offline evaluator paces calls outside answer timing; warm-up is not established.
- `Dockerfile.api` creates an unprivileged `app` user, fixes `HF_HOME=/app/.cache/huggingface` so
  the build-time model preload stays readable after `chown`, switches to that user, and adds a
  stdlib-only `HEALTHCHECK` against `/api/v1/health` (the slim image has no curl/wget).
- `requirements-dev.txt` (`-r requirements.txt` plus pytest, ruff, mypy) is the local/CI install;
  `requirements.txt` is runtime-only and is all the image installs. `httpx` stays in runtime
  because the Gemini/Groq providers use it. CI `backend` installs the dev file and `pip-audit`
  scans `constraints.txt`; `e2e` installs runtime only because it just boots uvicorn.
- `UPLOAD_RATE_LIMIT_PER_MINUTE` (default 20) caps `POST /uploads/preview` and
  `POST /analyses/{id}/rag/documents` per guest, sharing one budget, before any file is read;
  excess returns 429 with `Retry-After`. It reuses the generic `RagAnswerRateLimiter` class and its
  cleanup/shutdown wiring in `api/main.py`. Like the answer limiter, it keys on the guest cookie, so
  a client that discards cookies gets a fresh budget; it is a portfolio control, not abuse defense.

### Verification

- The public DataCo coverage audit reconciled its evaluated weekly opportunities and recorded the
  effects of the current policy, shorter history, and removing the zero-benchmark gate. See the
  [coverage audit](docs/evaluation/dataco_coverage_audit.md).
- The RAG Phase 2 hard-development evaluation preserved the locked set. Its real-provider run was
  inconclusive because Gemini returned quota/rate-limit failures; no retrieval or answer policy was
  tuned afterward. See the [hard-development report](docs/evaluation/rag_phase2_hard_development.md).
- A fresh hard-development rerun after local key rotation reached Gemini but was again inconclusive:
  one provider response and seventeen provider-unavailable cases, including rate-limit and service
  failures. The run also exceeded the five-second p95 gate. Its detailed trace is local-only under
  `data/private/`; the locked test remains untouched.
- For command-level verification and the latest test results, consult the relevant commit and
  evaluation report before claiming a check was rerun.
- GitHub Actions run 36324640711 on commit eba3658 (all work through the diagnostic rerun and
  refreshed docs): all four jobs passed (`backend`, `frontend`, `integration`, `e2e`). Locally on
  the same code, `ruff check .`, `ruff format --check .` (240 files), `mypy .` (99 source files),
  and bare `pytest -q -m "not integration"` (487 passed, 4 deselected) pass. Commit 02d8b92 alone
  fails 13 evaluation tests because it captured mid-edit test/script files; 3f5ba47 completes it.
  History was deliberately left unrewritten.
- Pre-testing hardening: GitHub Actions run 37159029027 on 80ef5d9 passed all four jobs. Locally:
  ruff, format, mypy, 503 backend tests, tsc, lint, build, and all 8 Playwright journeys against
  freshly started servers. The two concurrency tests were run against the previous commit and
  failed there (`['upload', 'health']`), proving they detect the bug; a first wall-clock version
  passed on the broken code too and was replaced.
- Correction: local Playwright runs reused any server already on port 8000, and a stale Python 3.9
  server from an earlier session was answering, so local browser results reported between
  2026-10-03 20:51 and the fix exercised old backend code. CI always starts fresh servers and was
  unaffected. `frontend/playwright.config.ts` now never reuses a server unless
  `E2E_REUSE_SERVER=1`; a busy port fails loudly.
- Phase 2 Stage A: GitHub Actions run 37155017748 on da4f757 passed all four jobs; in the `docker`
  job the container answered `/api/v1/health` on its second 5-second check (it had taken 463 s
  locally while downloading Olist). Locally: ruff, format, mypy, `pytest -q -m "not
  integration"` (490 passed), tsc, lint, build, and all 8 Playwright journeys, including the
  sample-retailer journey. A temporary Playwright check (not committed) confirmed the sample flow
  fits a 390 px phone at every step and works keyboard-only. The `integration` CI job was removed
  because its only four tests covered the removed Olist endpoints. The Docker image was not
  rebuilt locally because of a slow connection.
- Dashboard redesign: GitHub Actions run 37228957648 on c6b680d passed all four jobs (476 backend
  tests, 10 browser journeys). Locally: ruff, format, mypy, pytest, tsc, lint, build, and all 10
  journeys on fresh servers. Two new journeys cover sidebar jump links, the keyboard-only phone
  menu (Enter opens, Escape closes and returns focus, choosing a link closes it), and the
  open-at-top fix; with the fix removed they failed (opened 3,972 px and 5,219 px down). A
  scratch check (not committed) found no text below 12 px and no horizontal scroll at 390 px,
  and 44 px menu targets.
- Phase 2 Stage B: [GitHub Actions run 37221296252](https://github.com/tonysoftwarengineer/ecommerce-intelligence-sales-system/actions/runs/37221296252)
  on 90dfbfb passed all four jobs: backend, frontend, e2e, and docker. Locally,
  Ruff, format, mypy, 476 backend tests, TypeScript, frontend lint/build, and
  eight isolated browser journeys passed. A fresh Python 3.12 environment
  passed the full backend suite before its resolved versions were frozen;
  the new lock matches that environment. The four untracked PNG screenshots
  in `tests/fixtures/product_demand_csv_pack/` were not staged or changed.
- Phase 1 hardening: GitHub Actions run 36386997515 on 99844a7 passed all four jobs. Locally,
  ruff, format (240 files), mypy (99 files), `pytest -q -m "not integration"` (489 passed,
  4 deselected), and all eight Playwright journeys passed. The image was built and run locally
  (OrbStack): the process ran as uid 999 `app`, Docker health settled to `healthy` after the
  start period, and `/api/v1/health` returned 200. The image has not been deployed anywhere.
- For the dependency pass, exact `npm ci`, `npm audit --audit-level=high` (zero findings), frontend
  TypeScript, lint, build, and all eight Playwright journeys passed locally. The fresh Python audit
  still reported 57 findings in 14 packages; official PyPI resolver checks rejected the listed
  fixed `python-multipart`, `python-dotenv`, and `pytest` versions on Python 3.9.
- Groq adapter unit tests cover provider selection, missing keys, Bearer authentication, strict JSON
  schema requests, limited provider payloads, HTTP 429/503 handling, and malformed responses. The
  full non-integration suite, frontend checks, and eight isolated fake-provider browser journeys
  passed during the implementation.
- One Groq hard-development run preserved the locked split and returned seven verifier-approved
  answers. It was inconclusive: eleven provider-unavailable cases (ten 429 responses and one 400)
  left gold-claim coverage incomplete; one returned answer also missed an expected claim. The
  public report now labels upstream availability as inconclusive/release-blocked rather than a
  verifier-quality failure. Unsupported abstention, scope isolation, and the latency gate passed.
  See the sanitized [Groq report](docs/evaluation/rag_phase2_groq_hard_development.md); its
  detailed trace remains local-only.
- The fresh paced Groq run returned 15 provider responses; every returned answer passed exact-quote
  verification and unsupported abstention remained 100%, with no scope leakage or empty retrieval.
  It remains inconclusive: three provider failures (`400` once, `429` twice) and 57.1% reference
  coverage. Its recorded 5.96-second p95 includes pacing waits and cannot establish true warm
  processing latency. The original report and scores are preserved. See the separate sanitized
  [2026-09-27 Groq report](docs/evaluation/rag_phase2_groq_hard_development_2026-09-27.md); the
  detailed trace is local-only.
- RAG operational-control tests cover output caps, optional provider usage, six allowed
  provider-backed requests followed by a local HTTP 429 and `Retry-After`, unsupported-question
  budget preservation, privacy-safe aggregate metrics, and paced offline provider calls.
- The operational-control edge-case repair passed focused backend tests (71), Ruff, frontend
  type-check/lint/build, and all eight fake-provider Playwright journeys. No real provider or
  locked evaluation was run.
- The diagnostics repair passed `pytest -q -m "not integration"` (487 passed,
  4 deselected), Ruff checks, format checks (239 files), and mypy (99 source files).
  The run reports the existing Python 3.9 LibreSSL/urllib3 warning. It made no real
  provider calls and ran no locked evaluation or browser suite.
- Offline reconstruction resolved every selected chunk ID in the five incomplete
  answered development cases: three lacked the required reference passage and two
  had it. The old trace lacks generated claims for all five, so answer-level causes
  remain unresolved. Full reference coverage stays 12/21 (57.1%); the supplemental
  answered subset is 12/17 (70.6%), not a replacement release score.
- The fresh diagnostic rerun completed all 20 development cases once: eight
  verifier-approved answers, ten provider failures (nine `groq_request_failed`,
  one HTTP 400), zero HTTP 429s, 100% unsupported abstention, and zero scope leakage.
  Full reference coverage was 6/21 (28.6%); the provider-available subset was
  6/8 (75%). Both returned answers marked incomplete had correct supporting quotes
  from alternative approved documents. Current scores were preserved, not revised.
- All eight generated payloads/verified claim sets were captured. Processing p95
  was 5.144 seconds excluding 456.939 seconds of pacing; warm-up was not established.
  All source/configuration/fixture hashes checked before and after the run matched.
  The 37 focused evaluation/provider tests passed before the run. No automatic retry,
  stability run, locked run, model switch, or retrieval/prompt change occurred.

### Current limitations

- Product-demand forecasts are deliberately preview-only. The DataCo audit exposed cold-start and
  data-fit limitations; it did not relax or replace the trust gate.
- A permissioned, anonymized export from one independent online retailer is still required for the
  intended-audience forecasting checkpoint.
- RAG Phase 2 answers are experimental. Gemini quota/rate limits and the first Groq development
  run's 429/400 provider failures prevented conclusive scoring. The untouched locked Phase 2
  evaluation has not run, and the Groq result is not evidence of reliable answer quality.
- Literal reference matching is not semantic completeness or entailment. The old
  private trace stored a wrapper placeholder instead of claims; its missing answers
  and processing-only latency cannot be recovered. The new trace captured answers:
  two scored misses were supported by alternative sources that the development
  references do not accept. Do not infer model omissions from these two misses.
- The fresh run's nine transport errors lack exception-subtype metadata, so their
  root cause remains unknown. The user reported a network interruption, but it does
  not establish every failure's cause. The HTTP 400 is also undiagnosed. No supported
  multi-document case returned an answer in this attempt; their completeness and
  full-suite provider quality remain unverified.
- Sessions, uploads, document indexes, and analysis state are temporary and process-local; this is
  not a production multi-tenant deployment.
- `mypy` does not check `tests/`; test behavior is enforced by pytest only.
- The dependency audits remain report-only. The frontend lockfile audits cleanly. On
  2026-10-04, `pip-audit` reported **15 findings in 3 embedding/index packages** before and
  after Stage B (the earlier snapshot recorded 11; the advisory database changed).
  This phase did not change `chromadb`, `transformers`, or `sentence-transformers`.
  Fixes require a separate benchmarked embedding-stack upgrade; see the historical
  [triage record](docs/evaluation/dependency_security_triage.md).
- The answer cache, daily budget, and feedback counts are process-local: they reset on restart and
  are not shared across replicas. Feedback votes are visible only via the token-guarded
  observability endpoint; written feedback lives in public GitHub issues.
- Validation errors render at the top of the workspace, far from the button the user clicked,
  so on a long page an error can look like nothing happened. Noted, not changed.
- Starlette 1.7 warns that its test client will move from `httpx` to `httpx2` (test-only).
  Adding that dependency needs the user's approval.
- After changing any dependency, regenerate `constraints.txt` from a fresh Python 3.12
  environment that passes the full suite (instructions in its header). Local development uses
  `.venv` (Python 3.12); the system `python3` on this Mac is still 3.9, so use `.venv/bin/...`.
- The workflow still builds the frontend with Node 20 (`node-version: "20"` in `ci.yml`). Separately,
  GitHub warns that the JavaScript runtime of the actions themselves (`actions/checkout@v4`,
  `setup-node@v4`, `setup-python@v5`) is Node 20 and is being forced onto Node 24; that is the
  actions' own runtime, not the app's Node version.
- The repository is public; keep `.env`, `data/private/`, and any private evaluation traces out of
  Git. A tracked-file secret-pattern scan was clean before the first push.

### Next recommended work

1. **Phase 2 deploy.** One replica only (stores are process-local). Set `GUEST_COOKIE_SECURE=true`,
   exact `CORS_ORIGINS`, keep `DEVELOPMENT_OBSERVABILITY_ENABLED` off, and verify the guest-session
   cookie works when frontend and API are on different domains. Hosting choice and any paid tier
   are the user's decisions. Then the README rewrite: one-line pitch, live link, short demo video,
   architecture diagram, results table including the failed sparse stratum, honest limitations.
2. **PDF/HTML document support** as its own phase with an ADR: text extraction only (no OCR),
   strip HTML scripts and hidden elements (prompt-injection risk), size/page caps, parser CVE
   review, and an evaluation set with real PDFs before claiming support (AGENTS.md rule).
3. **AI explanation of the Python calculations** (later, own ADR): the model may only narrate
   numbers the code produced, each cited and verified by exact match; it never calculates.
4. Embedding-stack upgrade (`sentence-transformers`/`transformers`, review `chromadb`) as its own
   phase, with the frozen retrieval benchmark before and after; clears most remaining findings.
5. Consider bumping the GitHub Actions versions to clear the Node 20 deprecation warnings.
6. Obtain and safely prepare a permissioned, anonymized independent-retailer export, then run the
   existing offline evaluator without changing forecast policy after seeing its results.
7. Propose an offline development-reference audit of alternate passages supporting
   the same fact, with explicit scope/exception checks. Keep current scores and locked
   references unchanged; version any later scoring change separately. Investigate
   transport reliability and the undiagnosed Groq `400` with bounded diagnostics before
   another provider run. Do not switch models or add hybrid retrieval just to raise
   coverage. Stability/locked runs remain blocked pending complete development evidence.
8. Treat any cold-start forecasting improvement as a separate user-approved design and evaluation
   phase; do not loosen the live preview rules merely to increase coverage.

### Decisions requiring the user

- Whether an appropriate independent-retailer export can be obtained and used for the pending
  forecasting checkpoint.
- Whether to begin a separate cold-start product forecasting design phase before that checkpoint.
- Whether to run the untouched RAG Phase 2 locked evaluation after a provider passes every
  hard-development gate.
- Whether to approve the offline development-reference audit and separately scoped
  transport/HTTP-error diagnostics before another real-provider run.

## Detailed References

- [Product roadmap](docs/DIAGNOSTIC_INTELLIGENCE_ROADMAP.txt)
- [Architecture case study](docs/ARCHITECTURE_CASE_STUDY.md)
- [Product-demand locked evaluation](docs/PRODUCT_DEMAND_LOCKED_EVALUATION.md)
- [DataCo coverage diagnosis](docs/evaluation/dataco_coverage_audit.md)
- [RAG Phase 1 locked retrieval evidence](docs/evaluation/rag_phase_1/chroma_locked_test.md)
- [RAG Phase 2 hard-development report](docs/evaluation/rag_phase2_hard_development.md)
- [RAG Phase 2 Groq hard-development report](docs/evaluation/rag_phase2_groq_hard_development.md)
- [RAG Phase 2 Groq hard-development report — 2026-09-27](docs/evaluation/rag_phase2_groq_hard_development_2026-09-27.md)
- [RAG Phase 2 offline diagnostics review](docs/evaluation/rag_phase2_diagnostics_review.md)
- [RAG Phase 2 fresh diagnostic rerun and manual review](docs/evaluation/rag_phase2_groq_hard_development_diagnostics_rerun_2026-09-27.md)
- [RAG Phase 2 architecture decision](docs/architecture/ADR-015-experimental-grounded-document-answers.md)
- [Dependency security triage](docs/evaluation/dependency_security_triage.md)
