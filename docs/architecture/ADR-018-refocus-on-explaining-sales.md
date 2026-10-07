# ADR-018: Refocus on explaining sales numbers

**Status:** Accepted
**Date:** 2026-10-07
**Decider:** Project owner

## Decision, in the owner's words

The project is for online retailers who want to see their revenue, how many sales and orders they
have made, and whether their revenue went up or down compared to the previous month, and to be able
to ask questions about the data with AI. They cannot easily see which categories and products bring
in their money, or whether sales come from new or returning customers. They need to understand the
numbers clearly to know what they can improve and how. The project helps them understand their
numbers, and the application helps them spot problems sooner so they can act on them.

The AI adds plain-words understanding for the user without bringing in too many technical terms.
The AI should never be the one calculating numbers.

I am removing the document Q&A feature because it has nothing to do with the numbers: it is just
someone putting in documents and answering questions. Product demand stays as a quiet preview
because we have not gotten a real retailer's dataset yet.

I will test it manually and also run evaluation tests.

## Context

Feedback from an engineer reviewing the project was that it was unclear why it needs AI, and that
the document-answer feature looked unrelated to the sales analysis. The document feature
(ADR-013 to ADR-015) answered questions about uploaded policy documents; its real-provider
evaluations stayed inconclusive. It was also the only user of `chromadb`, `sentence-transformers`
(and through it `torch`), and `scikit-learn`, which made the deployable image about 2.6 GB and
carried the remaining Python audit findings.

## Scope

Removed from the live product:

- Document upload, search, and AI answers (`src/rag/`, the `/rag/*` API routes, the dashboard
  "Ask about your documents" panel, their tests, fixtures, and evaluation scripts) and the
  dependencies only they used.
- The Top Customers card. The export identifies customers only by an ID the owner would have to
  look up elsewhere, so the card added little. Customer IDs are still read, because the planned
  new-versus-returning breakdown needs them.

Kept:

- Sales validation, analytics, the revenue estimate, diagnostics, categories, and regions (shown
  only when the export has a region column).
- Product demand, as an optional, clearly labelled preview.
- Guest-session isolation for uploads and analyses (the CSV part of ADR-013).
- The evaluation reports of the document feature, as history.

Next, as its own decision record: **Ask about your sales**. The owner asks a question in plain
English; Python calculates and validates every figure first; the AI only phrases those facts. The
boundary in ADR-005 still applies: the validated report is the only source of financial values, a
deterministic check verifies every number the AI states, and the AI does not claim real-world
causes for a change. This refocus covers revenue only; it adds no cost or profit figures.

## Consequences

- The product has one clear purpose, and the AI's role is tied to the sales numbers.
- The deployable image no longer needs an embedding model or `torch`, which makes hosting simpler.
- Retrieval and grounded-answer experience remains visible in Git history (tag `before-refocus`)
  and in `docs/evaluation/`, but it is no longer a running feature.
- ADR-014 and ADR-015 are superseded. ADR-013 is superseded for documents only. ADR-005's
  explanation boundary carries over to the new feature.
