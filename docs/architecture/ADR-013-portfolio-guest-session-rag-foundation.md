# ADR-013: Portfolio RAG Uses Isolated Ephemeral Guest Sessions

**Status:** Accepted  
**Date:** 2026-09-17  
**Decider:** Project owner

## Context

ADR-005 correctly requires authenticated tenants and durable document governance
before a production business release. This project is currently a public
learning-first portfolio demonstration. Requiring recruiters to create accounts
would add friction without improving the retrieval experiment, while leaving all
visitors in one unscoped store could expose one visitor's files to another.

The immediate goal is to evaluate a bounded RAG explanation layer with synthetic
or voluntarily uploaded non-sensitive documents. It is not a production customer
document service.

## Decision

The portfolio release will not require account authentication. The API will issue
an unpredictable HttpOnly guest-session cookie and scope every uploaded CSV,
analysis, and RAG source document to that session. Cross-session lookups return
the same not-found response as unknown objects.

RAG documents will:

- remain in process memory and expire automatically;
- accept only approved UTF-8 text and Markdown sources in this phase;
- carry a session owner scope, document ID, type, filename, content hash, version,
  byte count, and timestamps;
- be accessed through a repository interface that can later be replaced with a
  durable tenant-aware implementation; and
- remain untrusted evidence when passed to a future model.

The public demo will include a version-controlled evaluation corpus with grounded,
abstention, and prompt-injection cases. Full authentication, durable storage, and
organization membership remain mandatory before a production business release.

## Options Considered

### Option A: Add account authentication now

| Dimension | Assessment |
|---|---|
| Recruiter friction | High |
| Production similarity | High |
| AI-learning value | Low for the current phase |
| Complexity | Medium |

**Pros:** Provides durable user identity and a direct route to tenant authorization.  
**Cons:** Adds setup and UI work before retrieval quality has been validated.

### Option B: Use isolated ephemeral guest sessions

| Dimension | Assessment |
|---|---|
| Recruiter friction | Low |
| Cross-visitor isolation | Strong within the single-process demo boundary |
| Persistence | None by design |
| Complexity | Low |

**Pros:** Preserves a one-click demo while creating a real ownership boundary and
a replaceable repository contract.  
**Cons:** Sessions and documents disappear on restart and cannot represent business
memberships across devices.

### Option C: Keep only opaque object IDs

| Dimension | Assessment |
|---|---|
| Recruiter friction | Lowest |
| Cross-visitor authorization | Weak |
| Complexity | Lowest |
| Security evidence | Weak |

**Pros:** No implementation work.  
**Cons:** Possession of an upload or analysis ID is the only access check, and a
shared RAG index could leak documents across visitors.

## Trade-off Analysis

Option B is the smallest architecture that matches the portfolio constraint while
preserving the non-negotiable cross-visitor boundary. It deliberately does not
claim production tenancy. The retrieval layer can now be evaluated without
coupling it to a permanent database or account provider.

## Consequences

- Recruiters can use the demo without registration.
- Browser requests must include credentials and CORS must allow credentials only
  for configured origins.
- Losing or expiring the guest cookie makes previous temporary data inaccessible.
- Temporary data is not recoverable after process restart.
- Prompt-boundary instructions reduce risk but do not prove injection resistance;
  adversarial evaluation and deterministic output verification remain required.
- Production deployment still requires authentication, tenant authorization,
  durable storage, retention controls, rate limiting, and operational monitoring.

## Action Items

1. [x] Scope CSV uploads and analyses to HttpOnly guest sessions.
2. [x] Add an ephemeral, versioned RAG document repository and API.
3. [x] Add grounded, abstention, and prompt-injection evaluation cases.
4. [x] Define the provider-neutral untrusted-context prompt boundary.
5. [x] Implement and evaluate chunking, retrieval, thresholds, and reranking.
6. [ ] Add a typed explanation response and deterministic verifier.
7. [x] Add a dashboard evidence-search workflow after retrieval gates pass.
