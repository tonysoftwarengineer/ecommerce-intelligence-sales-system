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

Codex — 2026-09-23

### Completed phase

The committed portfolio MVP now includes the generic sales workflow, diagnostics, bounded
product-demand previews, RAG evidence retrieval, experimental grounded document answers, API,
frontend, browser coverage, and deployment scaffolding. The most recent completed research phase
was the DataCo public-data product-forecast coverage diagnosis.

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

### Verification

- The public DataCo coverage audit reconciled its evaluated weekly opportunities and recorded the
  effects of the current policy, shorter history, and removing the zero-benchmark gate. See the
  [coverage audit](docs/evaluation/dataco_coverage_audit.md).
- The RAG Phase 2 hard-development evaluation preserved the locked set. Its real-provider run was
  inconclusive because Gemini returned quota/rate-limit failures; no retrieval or answer policy was
  tuned afterward. See the [hard-development report](docs/evaluation/rag_phase2_hard_development.md).
- For command-level verification and the latest test results, consult the relevant commit and
  evaluation report before claiming a check was rerun.

### Current limitations

- Product-demand forecasts are deliberately preview-only. The DataCo audit exposed cold-start and
  data-fit limitations; it did not relax or replace the trust gate.
- A permissioned, anonymized export from one independent online retailer is still required for the
  intended-audience forecasting checkpoint.
- RAG Phase 2 answers are experimental. Gemini quota/rate limits blocked real-provider development
  scoring, and the untouched locked Phase 2 evaluation has not run.
- Sessions, uploads, document indexes, and analysis state are temporary and process-local; this is
  not a production multi-tenant deployment.

### Next recommended work

1. Obtain and safely prepare a permissioned, anonymized independent-retailer export, then run the
   existing offline evaluator without changing forecast policy after seeing its results.
2. When the Gemini provider is available, rerun the frozen hard-development RAG Phase 2 evaluation.
   Run the untouched locked evaluation only if its documented release gates are met.
3. Treat any cold-start forecasting improvement as a separate user-approved design and evaluation
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
