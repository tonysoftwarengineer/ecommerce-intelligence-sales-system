# Focused dependency security triage — 2026-09-24

This pass checked the dependency findings from [GitHub Actions run 35861101477](https://github.com/tonysoftwarengineer/ecommerce-intelligence-sales-system/actions/runs/35861101477) against the current Python 3.9 and Node 20 setup. The audits remain report-only. Findings are advisory reports, not proof that a particular vulnerable code path is reachable in this application.

## Fixed in this pass

| Package | Previous | Current | Result |
| --- | --- | --- | --- |
| `nanoid` (via Vite → PostCSS) | 3.3.16 | 3.3.19 | The sole lockfile change. A clean `npm ci` and `npm audit --audit-level=high` report zero vulnerabilities. |

## Blocked by Python 3.9

| Package | Findings | Reason |
| --- | ---: | --- |
| `python-multipart` 0.0.20 | 6 | The highest listed fix is 0.0.31; official PyPI requires Python ≥3.10 for releases after 0.0.20. Python 3.9 cannot resolve 0.0.32. The upload routes continue to use the current parser. |
| `python-dotenv` 1.1.1 | 1 | The listed fix is 1.2.2, which requires Python ≥3.10. The 3.9 resolver rejects it. |
| `pytest` 8.4.2 | 1 | The listed fix is 9.0.3, which requires Python ≥3.10. The 3.9 resolver rejects it. This is development tooling, not a runtime API dependency. |

The resolver checks used Python 3.9.6 and the official PyPI index with `pip install --dry-run --ignore-installed`. A future Python upgrade needs its own compatibility tests before these pins change. Package metadata: [python-multipart](https://pypi.org/project/python-multipart/0.0.32/), [python-dotenv](https://pypi.org/project/python-dotenv/1.2.2/), [pytest](https://pypi.org/project/pytest/9.0.3/).

## Deferred coordinated upgrades

| Area | Package and findings | Follow-up |
| --- | --- | --- |
| API stack | `starlette` 0.49.3 (5), `anyio` 4.12.1 (2) | Review FastAPI and Starlette together. Current FastAPI 0.128.8 requires Starlette `<1.0`, while the listed Starlette fixes start at 1.x. Include upload and session isolation regression tests. |
| RAG index | `chromadb` 1.5.9 (4), `orjson` 3.11.5 (1), `click` 8.1.8 (1) | Select a compatible Chroma stack and re-evaluate indexing, retrieval quality, and document isolation. The audit lists no fix version for the four Chroma findings. |
| Embeddings/ML | `transformers` 4.57.6 (5), `pillow` 11.3.0 (18), `torch` 2.8.0 (8), `filelock` 3.19.1 (2) | Upgrade as a tested embedding stack; preserve the frozen Phase 1 retrieval benchmark and compare results before accepting a model-stack change. |
| Shared HTTP dependencies | `urllib3` 2.6.3 (2), `requests` 2.32.5 (1) | Resolve with their consumers, including the RAG stack and public-data tooling, in an isolated Python environment. |

The 14 Python packages above account for all **57 findings** in the fresh `pip-audit -r requirements.txt` result. That count remains unchanged because this pass did not accept a Python dependency update. The frontend advisory is cleared. Re-run the audits when beginning each deferred upgrade; advisory databases and available releases may change.

## Verification

- The `nanoid` lockfile entry moved from 3.3.16 to 3.3.19; no direct dependency or runtime code changed.
- `npm ci`, `npm audit --audit-level=high`, TypeScript, lint, and build passed.
- Playwright's eight browser journeys passed on isolated local ports with the fake RAG provider.
- The Python audit was repeated with `pip-audit==2.9.0` from a temporary environment and still reported 57 findings in 14 packages.

This result does not change forecast or RAG release status. Product demand remains preview-only, and RAG Phase 2 remains experimental.

## Update 2026-09-28: Python 3.12 runtime

The runtime moved from Python 3.9 to 3.12 ([ADR-016](../architecture/ADR-016-python-3-12-runtime-and-dependency-lock.md)).
The three Python-3.9-blocked fixes above are now applied: `python-multipart`
0.0.32, `python-dotenv` 1.2.3, and `pytest` 9.1.1. On 3.12 the transitive
`pillow`, `torch`, `anyio`, `filelock`, `urllib3`, `requests`, `orjson`, and
`click` findings also resolve to fixed releases. Those versions are now locked in
`constraints.txt`, which CI's `pip-audit` step scans.

| Stage | Known vulnerabilities |
| --- | ---: |
| Python 3.9, original pins | 57 in 14 packages |
| Python 3.12, this change | 14 in 3 packages |

Remaining: `starlette` (5), handled by the separate FastAPI/Starlette upgrade;
`transformers` (5), which needs `transformers` 5 and therefore a newer
`sentence-transformers`, an embedding-stack change that requires its own
benchmarked phase; and `chromadb` (4), which has no fixed release. Counts come from
`pip-audit==2.9.0 -r constraints.txt` on Python 3.12.13.

### API stack follow-up

`fastapi` 0.141.1, `uvicorn` 0.54.0, and `starlette` 1.7.0 (pinned directly,
because `fastapi` accepts `starlette>=0.46` and pip would otherwise keep 0.52.1)
cleared all five `starlette` findings. The same audit then reported two
advisories that were not in earlier runs, against versions this change did not
touch: `PYSEC-2026-4164` (`sentence-transformers` 5.1.2, fixed in 5.6.0) and
`PYSEC-2026-4174` (`transformers` 4.57.6).

| Stage | Known vulnerabilities |
| --- | ---: |
| Python 3.12 runtime | 14 in 3 packages |
| Plus API stack upgrade | 11 in 3 packages (`transformers` 6, `chromadb` 4, `sentence-transformers` 1) |

All remaining findings sit in the embedding/index stack, which needs its own
benchmarked upgrade phase. `chromadb` still has no fixed release.
