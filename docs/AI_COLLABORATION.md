# AI Collaboration & Handoff

## Purpose

This project is worked on by more than one AI coding tool — currently Codex and Claude Code —
relaying on the same local repository. Neither tool can see the other's conversation history or
session state; the only things both can see are **this filesystem** and **git history**. This file
exists to make that relay safe: whichever tool picks up work next should be able to reconstruct
where things stand without the user having to re-explain it.

Both tools already read [`AGENTS.md`](../AGENTS.md) automatically — that file is the shared
engineering contract (boundaries, financial/ML/RAG trust rules, working method, verification
commands) and this file does not repeat it. Read `AGENTS.md` first; this file only covers
session-to-session handoff mechanics.

## Start-of-session checklist (either tool, every session)

1. Read `AGENTS.md`.
2. Run `git status` and `git log --oneline -15` to see what's committed, what's modified, and what
   the last few phases were.
3. Read the **Current Handoff Notes** section at the bottom of this file.
4. If the working tree has uncommitted changes you didn't just make, treat them as in-progress
   work to preserve, not scratch state — per `AGENTS.md`'s git safety rules.

## End-of-session checklist (either tool, before finishing a work session)

Update **Current Handoff Notes** below with:
- Who made the change (Codex / Claude Code) and the date.
- What changed, in a sentence or two per area touched.
- What was actually tested/verified (which commands ran, what passed) — not just "looks right."
- What remains unverified or explicitly out of scope for this session.
- Any open decision that needs the user's `proceed` before continuing (per `AGENTS.md`'s
  Collaboration Contract).

## Commit discipline

Commit in the same bounded-phase style already visible in this repo's history (`V3` → `V5`, then
`Phase A/B/C`). A phase should be small enough to review and test on its own. Note which tool
authored a phase in the commit body (e.g. `Authored-by: Codex` or the Claude Code attribution
trailer) so `git log` alone tells either tool, or the user, what happened without needing this
file's notes to go back further than the last session.

Per standing git-safety rules, neither tool commits without the user explicitly asking for it in
that session — approval doesn't carry over from a previous session or from the other tool.

## Conflict avoidance

Treat Codex and Claude Code as a **relay, not concurrent editors**. Don't run both against the same
uncommitted files at the same time — pick one active tool per work session. If the user is
switching tools because one ran out of usage mid-task, the incoming tool should read the checklist
above before touching anything the outgoing tool left uncommitted.

## Current Handoff Notes

**Last updated by:** Claude Code — 2026-09-22

**What changed:** No code changes this session. Did a full architecture review (backend domain in
`src/`, API/infra/tests in `api/`+`tests/`+CI+Docker, frontend+docs in `frontend/`+`docs/`) and
created this handoff file. Full findings were given to the user in chat, not saved as a doc.

**What's verified:** Nothing new — this was a read-only review session, no tests were run.

**What's next / open for the user:**
- The working tree has ~103 untracked files/dirs representing most of the "generic business"
  product (CSV pipeline, diagnostics, product-demand forecasting, RAG, guest sessions, and
  ~9,700 lines of tests) that has never been committed — only the original Olist demo (14 commits,
  `V3`→`V5` + Phase A/B/C) is in git history. Recommend committing in reviewable phases before
  handing further work to either tool (see the review notes for a suggested grouping mirroring the
  existing ADRs).
- The `.env` file has a live-looking Gemini API key in plaintext. It has never been committed (it's
  gitignored), but since it's been read during this review, rotate it as a precaution.
- CI (`.github/workflows/ci.yml`) doesn't run `@pytest.mark.integration` tests, the Playwright e2e
  suite, or any dependency audit — worth closing before relying on CI as the safety net during
  tool handoffs.

**Open questions for the user:** None blocking — the above are recommendations, not decisions
requiring immediate input.
