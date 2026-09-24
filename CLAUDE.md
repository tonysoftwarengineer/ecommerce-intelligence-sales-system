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

Claude Code — 2026-09-24 (also contains Codex's uncommitted 2026-09-23 RAG rerun notes)

### Completed phase

The committed portfolio MVP now includes the generic sales workflow, diagnostics, bounded
product-demand previews, RAG evidence retrieval, experimental grounded document answers, API,
frontend, browser coverage, and deployment scaffolding. The most recent completed research phase
was the DataCo public-data product-forecast coverage diagnosis.

The repository is now on GitHub (public: `tonysoftwarengineer/ecommerce-intelligence-sales-system`,
remote `origin`, branch `main`). The CI coverage gaps from the architecture review are closed and
proven on GitHub's runners: `.github/workflows/ci.yml` runs integration tests and the Playwright
browser suite as their own jobs, and runs `pip-audit` / `npm audit` as report-only steps.

### Changed areas

- The generic business workflow remains: CSV upload, explicit mapping, validation and quarantine,
  canonical transformation, analytics, diagnostics, and capability-gated dashboard features.
- Product demand remains a seven-day, units-only planning preview. The DataCo audit investigated
  low coverage without changing its methods, eligibility rules, API, or dashboard trust gate.
- RAG Phase 1 retrieval is frozen and independently usable. Phase 2 adds claim-level grounded
  answers with exact support quotes and deterministic citation verification, but remains
  experimental.
- Deployment and portfolio documentation are committed. Use the linked reports for detailed
  findings rather than copying evidence into this snapshot.
- CI (`.github/workflows/ci.yml`) now has four jobs: `backend` (lint, format check, mypy, unit
  tests, `pip-audit`), `integration` (needs `backend`; `pytest -q -m integration`), `frontend`
  (tsc, `npm run lint`, build, `npm audit`), and `e2e` (needs `backend` + `frontend`; Playwright against the fake
  RAG provider and tfidf retrieval backend, no real key needed).
- Quality-gate fixes: all 15 files that failed `ruff format --check` were reformatted (cosmetic
  only); `scripts/__init__.py` was added so mypy resolves `scripts.<name>` once; mypy now excludes
  `tests/` (`pyproject.toml`, `exclude = ["^tests/"]`) because 59 pre-existing errors were all
  loosely typed JSON fixtures in tests, none in `src/`, `api/`, or `scripts/`; and
  `pythonpath = ["."]` was added to pytest config because bare `pytest` (the documented command)
  could not import `src`/`api`/`scripts` on CI.

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
- GitHub Actions run 35861101477 on commit e065f17: all four jobs passed (`backend`, `frontend`,
  `integration`, `e2e`). Locally, `ruff check .`, `ruff format --check .`, `mypy .` (97 source
  files), and bare `pytest -q -m "not integration"` (443 passed, 4 deselected) all pass.

### Current limitations

- Product-demand forecasts are deliberately preview-only. The DataCo audit exposed cold-start and
  data-fit limitations; it did not relax or replace the trust gate.
- A permissioned, anonymized export from one independent online retailer is still required for the
  intended-audience forecasting checkpoint.
- RAG Phase 2 answers are experimental. Gemini quota/rate limits blocked real-provider development
  scoring, and the untouched locked Phase 2 evaluation has not run. Do not spend further provider
  quota on repeated hard-suite runs until availability is stable.
- Sessions, uploads, document indexes, and analysis state are temporary and process-local; this is
  not a production multi-tenant deployment.
- `mypy` does not check `tests/`; test behavior is enforced by pytest only.
- The report-only dependency audits flag untriaged findings and do not block CI by design. In run
  35861101477, `pip-audit` reported 57 known vulnerabilities in 14 packages, including direct pins
  `chromadb`, `python-multipart` (parses the CSV/document uploads), `python-dotenv`, and `pytest`,
  plus transitive `starlette`, `anyio`, `transformers`, `pillow`, `click`, and `orjson`. `npm audit`
  reported one high-severity `nanoid` advisory (fix available via `npm audit fix`). Versions are
  exact-pinned, so each bump needs its own test run.
- The workflow still builds the frontend with Node 20 (`node-version: "20"` in `ci.yml`). Separately,
  GitHub warns that the JavaScript runtime of the actions themselves (`actions/checkout@v4`,
  `setup-node@v4`, `setup-python@v5`) is Node 20 and is being forced onto Node 24; that is the
  actions' own runtime, not the app's Node version.
- The repository is public; keep `.env`, `data/private/`, and any private evaluation traces out of
  Git. A tracked-file secret-pattern scan was clean before the first push.

### Next recommended work

1. Triage the audit findings, starting with `python-multipart` (upload parsing on a public API) and
   `starlette`/`fastapi`; bump exact pins one at a time and rerun the full suite. Decide which of
   the rest to fix now versus track.
2. Consider bumping the GitHub Actions versions to clear the Node 20 deprecation warnings.
3. Obtain and safely prepare a permissioned, anonymized independent-retailer export, then run the
   existing offline evaluator without changing forecast policy after seeing its results.
4. When Gemini availability is stable, rerun the frozen hard-development RAG Phase 2 evaluation
   three times. Run the untouched locked evaluation only if every documented development gate passes.
5. Treat any cold-start forecasting improvement as a separate user-approved design and evaluation
   phase; do not loosen the live preview rules merely to increase coverage.

### Decisions requiring the user

- Whether an appropriate independent-retailer export can be obtained and used for the pending
  forecasting checkpoint.
- Whether to begin a separate cold-start product forecasting design phase before that checkpoint.
- Whether to run the untouched RAG Phase 2 locked evaluation after Gemini availability and the
  hard-development gates are satisfied.

## Detailed References

- [Product roadmap](docs/DIAGNOSTIC_INTELLIGENCE_ROADMAP.txt)
- [Architecture case study](docs/ARCHITECTURE_CASE_STUDY.md)
- [Product-demand locked evaluation](docs/PRODUCT_DEMAND_LOCKED_EVALUATION.md)
- [DataCo coverage diagnosis](docs/evaluation/dataco_coverage_audit.md)
- [RAG Phase 1 locked retrieval evidence](docs/evaluation/rag_phase_1/chroma_locked_test.md)
- [RAG Phase 2 hard-development report](docs/evaluation/rag_phase2_hard_development.md)
- [RAG Phase 2 architecture decision](docs/architecture/ADR-015-experimental-grounded-document-answers.md)
