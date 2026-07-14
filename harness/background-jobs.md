# Background & long-running work

## Principle

Any work that must survive a restart, or that takes longer than a request should
block for, does **not** belong in an in-process, fire-and-forget task. Give it a
durable queue and a worker that owns it.

## When in-process tasks are wrong

Framework "background tasks" (FastAPI/Starlette `BackgroundTasks`, a bare
`asyncio.create_task`) run inside the web process and die with it. If the
process restarts mid-job, the job is silently lost and the row is stranded in a
"processing" state forever. Fine for best-effort side effects (fire a metric);
wrong for anything a user is waiting on or that must complete.

## The durable-queue pattern (no new infrastructure)

You usually already have the queue: your database.

- **Enqueue, don't do.** The request validates cheaply, writes the job row as
  `queued`, and returns immediately (e.g. `202` + an id to poll). Heavy work
  happens elsewhere.
- **Claim atomically, safe for N workers.** A dedicated worker process claims one
  job with `SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1` (flip to `processing`,
  stamp `claimed_at`) — concurrent workers never grab the same row.
- **Never strand a job.** On worker startup (and periodically), requeue rows
  stuck in `processing` past a generous stale window (`claimed_at < now() -
  interval`) — a crashed worker's job comes back. Record failures on the job
  (`status='failed'` + reason), never drop them.
- **Run the worker as its own process/container**, on the same image. The web
  process no longer loads the heavy libs, so its footprint shrinks; the worker
  carries them. Scale workers horizontally — `SKIP LOCKED` makes it safe.
- **Client polls** the job's status endpoint until it leaves the queue; show an
  honest busy state (elapsed time, not a fake progress bar).

## Verify it for real

Migrations + claim/reclaim SQL (locks, intervals, partial indexes) must be
exercised against a real database, not just compiled — spin up a throwaway
Postgres and drive enqueue → claim → finalize → stale-reclaim (see
`testing-verification.md`). Keep the worker's processing function callable
directly so tests can drive it deterministically.

**On this project:** `catalog.extraction_runs` is the queue (`queued` status,
`claimed_at`), `ingestion/worker.py` is the worker (`python -m ingestion.worker`,
its own `ingestion-worker` compose service), and the upload endpoint only
enqueues. `WORKER_STALE_SECONDS` (default 1800) bounds the reclaim window.
