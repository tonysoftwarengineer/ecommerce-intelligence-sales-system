# RAG Phase 2 development diagnostics repair

## Result and boundaries

This is an offline review of the existing 2026-09-27 Groq hard-development
artifacts, not a new provider evaluation or an answer-quality improvement.
No provider calls, locked evaluation, model changes, prompt changes, retrieval
changes, or forecast changes were made. The
[original report](rag_phase2_groq_hard_development_2026-09-27.md) and its scores
remain historical evidence and have not been overwritten.

## What the original measurement establishes

- Full-suite reference-passage coverage remains **12/21 = 57.1%**.
- Three provider-unavailable cases account for four reference passages.
- Supplemental coverage across the 15 answered supported questions is
  **12/17 = 70.6%**. The two deliberately unsupported questions are not included
  in either reference-passage denominator. This is not a replacement release score.
- All 15 returned answers passed the existing citation/exact-quote verifier.
  That verifies quote/citation binding, not semantic completeness or entailment.
- The old `retrieval_miss_count = 0` means no supported question returned an
  empty evidence set. It does **not** establish that all required facts reached
  the answer model.
- An HTTP 400 remains an undiagnosed provider rejection. Its status alone does
  not prove that our request was malformed.

## Offline reconstruction of the five incomplete answered cases

The eight synthetic development documents were re-chunked with the recorded
224-token limit and 32-token overlap. Every selected chunk ID in these five
cases was reconstructed successfully. Reference-passage checks required both
the expected document and matching text in the selected chunk.

| Finding | Answered cases |
|---|---:|
| Missing required reference passage in selected evidence | 3 |
| Required reference passage present, but not matched by answer scoring | 2 |
| Generated claims unavailable in the old trace | 5 |

The old tracer attempted to serialize `ProviderGeneration` rather than its
payload and saved a type placeholder. Therefore answer-level explanations
remain **unresolved** for all five cases. In particular, the two evidence-present
cases cannot yet be classified as genuine fact omissions versus shorter valid
support quotes that did not contain the entire reference wording. Even the three
evidence-absent findings concern literal reference passages, not a separate
semantic-equivalence judgment.

## Diagnostic changes for future runs

- Save the provider payload and verified claims separately in ignored local
  traces, retaining invalid JSON-shaped payloads for investigation.
- Record reference-passage availability and selected chunk IDs per gold fact.
  Empty retrieval, missing reference evidence, provider outages, verifier
  rejections, and answer/reference mismatches are distinct; findings may overlap.
- Keep the full-suite coverage formula and all release thresholds unchanged.
  Supplemental provider-available coverage includes supported returned payloads,
  including verifier rejections. Outages and retrieval-withheld cases are
  excluded from that supplemental denominator only. Empty supplemental
  denominators are reported as not assessed, not 100%.
- Pace expected provider calls before timed answer generation. Record pacing
  delay separately from retrieval + generation + verification latency. The
  five-second threshold and legacy `warm_p95_latency` key remain unchanged,
  but reports explicitly say that warm-up has not been established.
- CLI trace destinations must remain under ignored `data/private/`.

The original **5.96-second p95 includes intentional pacing waits**. Its true
processing-only p95 cannot be recovered from the old trace. Do not retroactively
mark that gate passed or claim the reported figure measures warm interactive
latency. Future complete runs use the corrected timing scope.

## Verification and next safe task

Deterministic tests cover wrapped and unwrapped payloads, verifier rejections,
provider exceptions, nonempty incomplete evidence, partial multipart coverage,
overlapping findings, supplemental denominators, intentional pacing, unsupported
abstention, and aggregate-only report rendering. No real-provider quality claim
is made by these tests.

Completed checks: `pytest -q -m "not integration"` passed with **487 tests** and
4 deselected; `ruff check .`, `ruff format --check .` (239 files), and `mypy .`
(99 source files) passed. The existing Python 3.9 LibreSSL/urllib3 warning remains.
The ignored local `.env` has observability disabled to satisfy Claude Code's
committed token guard without adding a new secret. No API/security edits from
Claude Code were reverted. Frontend/browser and integration checks were not rerun
for this evaluation-only repair.

Next, request a separately approved fresh, paced full development run with the
repaired traces. Inspect the evidence-present mismatches and the provider 400
using bounded diagnostics. Only then propose a targeted development retrieval
or generation experiment. Preserve the frozen baseline and untouched locked set;
do not weaken verification or redefine scoring to obtain a pass.
