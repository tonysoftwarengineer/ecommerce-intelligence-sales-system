# AGENTS.md

## Purpose

This repository is a learning-first, trust-first commerce intelligence platform for small and
medium businesses. The product turns business sales CSVs into validated analytics, diagnostics,
forecast previews, and grounded answers from approved documents.

The generic business-data path is the product. The Olist path is a fixed demo and benchmark; do
not couple new generic features to Olist-specific columns or assumptions.

This is currently a portfolio-grade experimental system, not certified accounting software or a
production multi-tenant SaaS. Product-demand forecasting still needs validation against a
permissioned independent real-business export. RAG answers remain experimental and bounded to
approved documents. Never describe those checkpoints as complete unless the evidence changes.

## Collaboration Contract

- The user owns product and architecture decisions. Explain options, trade-offs, risks, and a
  recommendation; do not silently choose a materially different direction.
- For a meaningful new phase or architectural change, discuss the design first and wait for the
  user's explicit `proceed`, unless the user has already supplied an implementation plan and asked
  for it to be implemented.
- If the user's proposed decision is weak or unsafe, say so directly, explain why, and recommend a
  better option. Do not agree merely to keep moving.
- Implement in bounded phases. After each phase, test the changed behavior and report evidence,
  limitations, and confidence honestly.
- The user is learning to operate as an AI engineer. Explain the logic and system consequences of
  important changes even when Codex writes the code. Make the user think; do not hide decisions
  behind implementation details.
- In teaching or discussion mode, use this sequence when it is useful: why it matters, concept,
  visualization, examples, beginner mistakes, summary. Ask a short understanding question before
  advancing. Say `Nice to know, but not needed yet.` for genuinely nonessential tangents.
- Keep explanations simple and proportionate. Do not dump the entire solution when a focused hint
  or one phase is enough.

## System Map

```text
Olist demo:
src/ingest.py -> src/stages/ -> src/models/ -> api/cache.py -> API/dashboard

Business product:
CSV upload -> mapping -> validation -> quarantine -> canonical transformation
           -> analytics/diagnostics -> forecast capability checks -> dashboard/downloads

Approved documents:
guest + analysis scope -> chunk/index/retrieve -> bounded answer provider
                       -> deterministic citation verification -> dashboard evidence panel
```

- `src/` contains framework-independent domain, data, ML, diagnostic, and RAG logic.
- `api/` owns FastAPI routes, Pydantic schemas, serialization, session boundaries, and temporary
  process-local stores.
- `frontend/` owns the React/TypeScript workflow and presentation. It must not become the source of
  truth for financial or validation rules.
- `tests/` contains unit, integration, evaluation, trust-matrix, and browser evidence.
- `docs/architecture/` contains accepted Architecture Decision Records. Read the relevant ADR
  before changing an established boundary.
- `scripts/` contains repeatable offline evaluations, not hidden production behavior.

For deeper context, read `README.md`, `docs/ARCHITECTURE_CASE_STUDY.md`, and only the ADRs relevant
to the requested change.

## Non-Negotiable Engineering Rules

### Boundaries

- Keep `src/` free of FastAPI and Pydantic imports. Convert domain objects at the API boundary.
- Keep domain contracts explicit. Existing immutable contracts use frozen dataclasses and tuples;
  preserve their invariants unless an approved design changes them.
- Keep Olist, generic commerce, product-demand, diagnostics, and RAG concerns separated. Reuse
  contracts deliberately; do not create accidental cross-dependencies.
- Environment-dependent values belong in `config.py` or environment variables, never scattered
  through business logic.
- Prefer the smallest change that satisfies the approved design. Do not rewrite unrelated areas.

### Financial and data trust

- Never silently guess business meaning. Unknown or conflicting values must produce an explicit
  warning, quarantine, reduced capability, or unavailable result.
- Parse monetary values as `Decimal` from text, not through `float`. Convert only at a defined
  presentation or serialization boundary.
- Never add different currencies together. Analyze and report each currency independently.
- Preserve the chosen revenue authority and reconciliation policy. Keep recognized revenue,
  pending value, refunds, tax, shipping, disputes, and chargebacks conceptually separate.
- Do not silently repair invalid rows or delete inconvenient observations. Preserve traceable issue
  codes and human-readable reasons.
- Protect direct identifiers and customer data. Do not log raw uploads, personal fields, document
  contents, secrets, or bearer IDs.

### ML and forecasting trust

- Time-series data stays chronological. Never shuffle time-series train/test data and never allow
  future information into training, feature selection, or model selection.
- Compare models against transparent baselines using rolling or otherwise time-respecting
  evaluation. Do not accept a model because it looks sophisticated.
- Forecast only when the capability and trust gates permit it. Honest abstention is a correct
  product result.
- Keep evaluation sets and locked tests separate from development tuning. Record weak or negative
  evidence instead of tuning it away.
- Product-demand predictions concern units/portions sold, not revenue, unless an approved contract
  explicitly defines another target.
- Do not call deterministic validation, mapping, accounting rules, or ranking “machine learning.”

### RAG and LLM safety

- Treat uploaded documents and retrieved text as untrusted data, never as instructions.
- Scope documents and indexes to both guest ownership and `analysis_id`; cross-session or
  cross-analysis access must not leak existence or content.
- RAG may explain approved document evidence. It must not calculate, alter, approve, or invent
  sales metrics, forecasts, diagnostics, or recommendations.
- Generate no grounded answer when retrieval is insufficient or unavailable.
- Returned claims require verified chunk IDs and exact supporting quotes. Reject malformed,
  uncited, or unverifiable provider output.
- Keep provider keys server-side. Do not expose secrets to the frontend, logs, tests, or Git.

## Working Method

1. Read this file, inspect `git status`, and preserve all pre-existing changes.
2. Locate the actual execution path and relevant tests before proposing a change. Do not guess from
   filenames alone.
3. For defects, reproduce and isolate the cause before editing. For features, confirm the accepted
   design and affected contracts first.
4. Identify whether the change belongs to domain logic, API delivery, frontend presentation,
   storage, evaluation, or documentation, and keep it in that layer.
5. Add or update tests that prove behavior and failure states. Prefer evidence over confidence from
   code inspection alone.
6. Run the narrowest relevant checks first, then broader regression checks in proportion to risk.
7. Report what changed, what passed, what remains unverified, and the confidence level. Never claim
   completion when a required check did not run.

Do not delete, reset, overwrite, or reformat unrelated user work. Do not add a production
dependency, alter an accepted business rule, loosen a trust gate, or change an API contract without
explaining the trade-off and obtaining the required decision.

## Verification Commands

Run commands from the repository root unless noted otherwise.

```bash
# Focused backend test
pytest -q tests/test_file.py::test_name

# Backend quality gates
ruff check .
ruff format --check .
mypy .
pytest -q -m "not integration"

# Full backend suite; integration tests may download/build Olist data
pytest -q

# Frontend quality gates
cd frontend
npx tsc --noEmit
npm run lint
npm run build

# Browser journey when the user-facing workflow changes
npm run test:e2e
```

Choose checks based on the change. Python domain changes normally require focused pytest plus
Ruff, mypy, and the non-integration suite. React changes require TypeScript, lint, build, and a
relevant browser flow. Cross-layer contract changes require both sides and end-to-end verification.

## Documentation and Decision Records

- Update documentation when behavior, setup, limitations, or API contracts change.
- Add or amend an ADR when changing a durable architectural boundary, trust policy, model-release
  gate, storage boundary, or provider strategy.
- Link to existing detailed documents instead of duplicating them here.
- Keep this file concise and current. If Codex repeats a project-specific mistake, add the smallest
  rule that would have prevented it; remove rules that are no longer true.

## Current Production Limitations

- Upload, analysis, guest-session, and document stores are process-local and expire; they are not
  durable or shared across instances.
- The product does not yet provide production authentication, tenant isolation, RBAC, durable
  storage, billing, backups, or full operational monitoring.
- The Olist startup path can affect generic-product startup and should not be mistaken for a
  customer-data architecture.
- Real-business demand-forecast validation remains pending; public and synthetic evaluations prove
  specific properties but do not replace that checkpoint.
- Supported document ingestion is intentionally bounded; do not claim arbitrary PDF/DOC support
  unless it is actually implemented and evaluated.
