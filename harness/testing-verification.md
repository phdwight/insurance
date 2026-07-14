# Testing & verification

## Principle

Tests must be **functional and cross-layer**, and a change isn't "done" until
you've **watched it work** — not just watched the unit tests go green.

## Functional, cross-layer tests

- Exercise **real flows**, not imports. Drive the endpoint/queue/SQL path the way
  the app does (e.g. upload over HTTP → assert the run reaches the right status →
  approve → assert it published).
- Trivial import-only or health-only tests are noise (fine as a smoke test for an
  empty skeleton service, not as coverage).
- **Fake at the seams, run the rest for real.** Monkeypatch the expensive/
  nondeterministic edges (LLM calls, embeddings, heavy parsers) at their module
  boundary; let the actual routing, validation, and persistence logic run. Force
  the deterministic light path where a heavy dependency would make the test slow
  or flaky.
- Keep them fast and deterministic — no network, no real model downloads, no
  wall-clock sleeps.

## Verify before "done"

Green tests prove the units; they don't prove the feature. Before claiming a
nontrivial change works, **drive the actual flow end-to-end and observe the
behavior**:

- Spin up the real dependency when feasible — e.g. a throwaway Postgres in a
  container to prove a migration applies and a new SQL query (locks, intervals,
  indexes) actually behaves, not just that the Python compiles.
- Build and run the real artifact when the change is in packaging/serving — e.g.
  build the image and hit the running container, don't infer from the Dockerfile.
- Reproduce the original symptom, then confirm it's gone.

## Report honestly

- If tests fail, say so, with the output.
- If a step was skipped or couldn't be verified in this environment, say that —
  don't imply coverage you didn't run.
- State what you verified and how ("exercised claim/reclaim against a real
  Postgres"), so the reader can trust or re-check it.

**On this project:** run `ruff check .` and `pytest` before committing; PWA
changes also need `npm run build`. After a `pyproject.toml` change, `uv lock`
and commit the lockfile (CI runs `--locked`). Tests fake LLM/embeddings/docling
at the module seams and force `DOCLING_ENABLED=false` for determinism.
