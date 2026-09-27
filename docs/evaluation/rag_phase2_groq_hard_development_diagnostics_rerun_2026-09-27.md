# RAG Phase 2 Answer Evaluation

- Provider: `groq_rest`
- Model: `openai/gpt-oss-20b`
- Suite: `hard-development`
- Split: `development`
- Cases: 20
- Verifier pass rate: 100.0%
- Unsupported abstention accuracy: 100.0%
- Gold-claim coverage (reference-passage matching): 28.6% (6/21)
- Supplemental provider-available coverage: 75.0% (6/8)
- Cross-scope leakage count: 0
- Processing p95 latency: 5144.4 ms
- Latency scope: retrieval + generation + verification; pacing excluded; warm-up not established
- Total intentional pacing delay: 456939.0 ms
- Provider-unavailable cases: 10
- Provider responses: 8
- Provider failure reasons: `groq_http_400`: 1, `groq_request_failed`: 9
- Verifier-rejected cases: 0
- Empty-retrieval cases (legacy retrieval_miss_count): 0
- Cases missing reference evidence: 4
- Answer/reference mismatches with evidence present: 1
- Evaluation conclusion: **inconclusive — provider availability prevented complete scoring**

| Release gate | Result |
|---|---|
| verifier pass rate | pass |
| provider availability | inconclusive (upstream provider failures) |
| unsupported abstention | pass |
| gold claim coverage | inconclusive (incomplete provider responses) |
| scope isolation | pass |
| processing p95 latency (legacy key: warm_p95_latency) | fail |

Provider-unavailable cases make a real-provider run inconclusive; they are not
treated as verifier or answer-quality failures. Gold-claim coverage is also
incomplete when a provider fails before producing an answer. A fresh run must
repeat the whole suite after the provider limit resets; it must not combine only
the later retries with this run. The grounded-answer feature remains
experimental unless every gate passes and every locked-test failure receives
manual review. A deterministic fake-provider result validates wiring and
verification only; it is not a real-provider quality claim.

Coverage checks reference passages inside cited support quotes, not semantic
answer completeness. Supplemental coverage includes supported cases with a
returned payload (including verifier rejections); provider-unavailable and
empty-retrieval cases are excluded. It never replaces full-suite coverage or
release gates. Diagnostic categories can overlap. The legacy warm_p95_latency
gate keeps its five-second threshold, but this run does not establish warm-up.

## Execution and preservation

This was one complete 20-question development attempt using Groq
`openai/gpt-oss-20b`, with a minimum 30-second interval between provider attempts.
There were no automatic retries, provider switches, cherry-picked reruns,
stability runs, or locked evaluations. Previous artifacts were not overwritten.
The JSON result and detailed trace remain under ignored `data/private/`.

Before the run, 37 focused evaluation/provider tests passed. The configuration
remained Chroma/MiniLM, 224-token chunks, 32-token overlap, a 0.4 relevance gate,
no lexical reranker, and a 1,024-token answer cap. Code and fixture hashes taken
before and after the run matched, including the answer prompt, retrieval logic,
provider adapter, and frozen evaluation fixtures.

## Manual review of every incomplete returned answer

Both returned answers marked incomplete were inspected against their generated
claims, exact support quotes, selected evidence, and gold reference passages.

| Finding | Count |
|---|---:|
| Returned answers with unmatched reference passages | 2 |
| Those answers supported by another approved document | 2 |
| Demonstrated fact omissions in those two reviewed answers | 0 |
| All supported cases missing the expected-document reference evidence | 4 |
| Those missing-reference cases also blocked by provider failure | 3 |

One reviewed answer correctly addressed failed-transfer stock reservation using
an explicit rule in another approved document. Its expected reference passage
was absent from the selected chunk of the expected document, but equivalent
support was present in the selected alternative document. The other correctly
addressed promotion/wholesale compatibility using an alternative policy quote;
the expected reference was also available, but the answer cited another source.

The scorer requires the specific gold document and reference wording in the
support quote. It therefore marked both as incomplete despite the manually
supported answers. This is evidence of overly narrow development references for
these two cases, not evidence that all low coverage is a scoring defect. No gold
references, scoring formulas, thresholds, or scores were changed. Full coverage
stays **6/21 (28.6%)**; supplemental provider-available coverage stays **6/8 (75%)**.
Do not publish a recalculated semantic-coverage percentage from this review.

All eight returned payloads and verified claims were captured successfully.
The other six returned answers matched their references and were inspected too.
No multi-document supported case produced an answer in this attempt, so this run
cannot establish multi-part answer completeness or stability.

## Availability, latency, and limitations

Nine failures were `groq_request_failed`, the adapter's bounded code for an HTTP
transport exception. The trace does not retain the exception subtype, so it cannot
distinguish connection, DNS, TLS, or timeout causes. The user reported a network
interruption during the attempt, but that does not prove the cause of every
failure. One HTTP 400 remains undiagnosed; its status alone does not establish a
malformed request. There were **zero HTTP 429 responses**. This result must not be
described as a confirmed quota/rate-limit failure or attributed solely to Groq.

All ten provider-unavailable cases returned no claims. Both deliberately
unsupported questions produced insufficient evidence with no generated payload
or claims. The verifier had no rejections among eight returned answers; this
checks exact-quote/citation binding, not full semantic entailment or production
safety. Scope probes returned zero cross-session or cross-analysis evidence.

Processing p95 across all twenty cases was **5.144 seconds**, excluding
**456.939 seconds** of intentional pacing. This exceeds the existing five-second
threshold. The eight successful answers individually took **0.847–2.178 seconds**;
the unavailable cases took **1.684–5.164 seconds**. These subsets explain the
measurement but do not replace the full-suite latency gate. Warm-up was not
established, and no production latency claim is made.

## Next recommended experiment

First perform a separately approved, offline development-reference audit: list
explicit alternate supporting passages for the same fact, checking scope,
exceptions, and contradictions. Keep the current scores and frozen/locked sets
as historical evidence; any later scorer/reference revision must be versioned
and reported separately rather than retroactively turning this run into a pass.
Do not add hybrid retrieval, a reranker, or a new model based on these two cases.

Before another paid/provider-backed run, investigate transport reliability and
the HTTP 400 using bounded diagnostic metadata, without retaining credentials or
document content. Any instrumentation or retrieval/generation experiment needs
its own approved scope. The current attempt remains **inconclusive**, the feature
remains experimental, and no stability or locked run is authorized by its result.
