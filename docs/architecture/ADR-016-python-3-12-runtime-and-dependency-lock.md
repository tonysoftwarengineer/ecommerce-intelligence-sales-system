# ADR-016: Python 3.12 Runtime and a Transitive Dependency Lock

**Status:** Accepted  
**Date:** 2026-09-28  
**Decider:** Project owner

## Context

The application ran on Python 3.9, which no longer receives security fixes. The
report-only `pip-audit` step found 57 known vulnerabilities in 14 packages. The
[dependency triage](../evaluation/dependency_security_triage.md) showed that the
listed fixes for `python-multipart`, `python-dotenv`, and `pytest` require Python
3.10 or newer, so no pin change could clear them on 3.9.

`requirements.txt` pins direct dependencies exactly, but transitive ones float.
Resolving the same pins on 3.12 moved `torch` from 2.8.0 to 2.14.0, `numpy` from
2.0.2 to 2.5.3, and `starlette` from 0.49.3 to 0.52.1 without any pin changing.
`torch` runs the RAG embedding model, so an unnoticed change there could alter
document retrieval.

## Decision

- Run the API, CI, and local development on Python 3.12.
- Raise the three Python-3.9-blocked pins: `python-multipart` 0.0.32,
  `python-dotenv` 1.2.3, `pytest` 9.1.1.
- Pin `numpy==2.4.6` directly. With `pandas==2.3.3`, NumPy 2.5 emits a
  deprecation warning from inside pandas' `Timedelta` constructor that NumPy
  says will become an error; 2.4.x is clean.
- Add `constraints.txt`: the exact versions of all 120 installed packages from an
  environment that passed the full suite. Docker and CI install with
  `-c constraints.txt`, and `pip-audit` scans it, so the audited, tested, and
  shipped versions are the same.
- Install CPU-only `torch` in the image and in CI from PyTorch's CPU index
  (`https://download.pytorch.org/whl/cpu`), reading the version from
  `constraints.txt`. On Linux, PyPI's `torch` 2.14.0 wheel pulls NVIDIA CUDA
  libraries (for example `nvidia_cudnn` 651 MB and `nvidia_cublas` 543 MB) that
  this CPU-only embedding workload never uses; an earlier 3.12 image that included
  them reported 3.75 GB. `2.14.0+cpu` satisfies the `torch==2.14.0` constraint
  under PEP 440.
- Keep the image lean: `.dockerignore` now excludes `.mypy_cache` (575 MB locally)
  and `.ruff_cache`, and application files are copied with `COPY --chown` to a user
  created first, replacing a `chown -R` step that duplicated every file into a
  roughly 700 MB layer. The measured image is 2.62 GB (mostly `torch` at 647 MB
  and other Python libraries in a 1.76 GB layer, plus the 92 MB embedding model).
- Upgrade the FastAPI/Starlette stack in a separate follow-up commit so it can be
  reverted independently.
- Leave `ruff` `target-version` at `py39` for now; raising it enables
  project-wide pyupgrade rewrites that belong in a separate cosmetic commit.

## Options Considered

### Option A: Python 3.11
**Pros:** Slightly more conservative.  
**Cons:** Not installed locally, so verification would rely on CI alone.

### Option B: Python 3.12
**Pros:** Installed locally, so every gate, the browser suite, the image build, and
the retrieval benchmark could be run before pushing. All existing pins resolve.  
**Cons:** Transitive libraries move, which is what the lock and benchmark address.

### Option C: Upgrade pandas to 3.x instead of pinning NumPy
**Pros:** Removes the NumPy cap.  
**Cons:** A major pandas release with behavior changes (copy-on-write, string
dtype); too broad for a runtime phase.

## Trade-off Analysis

The runtime move itself is low risk because every pin resolved unchanged. The real
risk was silent transitive drift, so the decision pairs the upgrade with a lock
and a before/after retrieval benchmark rather than trusting the test suite alone.
A lock adds a regeneration step to dependency changes; that cost is accepted in
exchange for reproducible installs.

## Consequences

- Known vulnerabilities: 57 (Python 3.9) to 14 after this change. The remaining
  findings are `starlette` (addressed by the follow-up commit), `transformers`
  (the fix needs `transformers` 5, which `sentence-transformers` 5.1.2 does not
  allow; that is an embedding-stack change needing its own benchmarked phase),
  and `chromadb` (no fixed release exists).
- The frozen RAG Phase 1 retrieval benchmark, development split with the frozen
  configurations, produced identical per-question results on 3.9 and 3.12 for
  both TF-IDF and Chroma, excluding latency. The same held for the benchmark run
  inside the built Linux image with CPU-only `torch`. The locked split was not
  rerun.
- While establishing the 3.9 baseline, the committed development reports
  (`docs/evaluation/rag_phase_1/*_development.md`) were found to be stale: chunk
  precision is 50.0% (TF-IDF) and 74.3% (Chroma) today versus 46.7% and 70.3%
  recorded, with identical configuration. Running the commits immediately before
  and after the only later code change (formatting) gave the same 50.0%, so the
  reports predate the committed code; this upgrade did not cause the difference.
  The historical reports are left unedited.
- Local development uses a Python 3.12 virtual environment in `.venv/`.

## Action Items

- [x] Python 3.12 in `Dockerfile.api`, CI, and mypy; three blocked pins raised.
- [x] `constraints.txt` added and used by Docker, CI, and `pip-audit`.
- [x] Retrieval benchmark before/after on the development split, on macOS and
      inside the Linux image.
- [x] CPU-only `torch` and a lean image (2.62 GB), run locally as uid 999 and
      reporting `healthy`.
- [ ] FastAPI/Starlette upgrade as a separate commit.
- [ ] Decide whether to regenerate the stale Phase 1 development reports.
- [ ] Later: embedding-stack upgrade (`sentence-transformers`/`transformers`) as its
      own benchmarked phase; raise the ruff target in a cosmetic commit.
