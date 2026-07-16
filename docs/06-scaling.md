# Scaling posture: poured slabs and growth triggers

Written at hobbyist scale, for the 10k-user day. The repo rule stands —
**abstractions on trigger, not speculation** — so this doc records (a) the
slabs already poured that make growth a config change instead of a rewrite,
and (b) the concrete signals that justify each next step. Don't build ahead of
a trigger; when one fires, this is the map.

## Already poured (works today, carries 10k users)

| Slab | Where | Why it matters at scale |
|---|---|---|
| Stateless services — all conversation state in Postgres (LangGraph checkpointer, per `session_id`) | `agent/main.py` | api/agent scale horizontally with **no sticky sessions**; any replica can serve any turn |
| Shared DB pool — checkpointer + caches + ledger on one `AsyncConnectionPool` (`AGENT_DB_POOL_SIZE`, default 10) | `agent/db.py` | a single shared connection would serialize every concurrent chat's state I/O; per-op connects would churn Postgres |
| Catalog TTL cache (`CATALOG_CACHE_SECONDS`, default 60; 0 = off) | `agent/mcp_client.py` | kills the per-turn search + `get_policy`×N MCP fan-out; staleness bounded to ~a minute |
| Token economy — outcome-bucket explanation cache, deterministic-parse-first, batched judges, `LLM_ECONOMY` ladder, spend ledger + `DAILY_TOKEN_BUDGET` | `agent/expl_cache.py`, `nodes.py`, `verifier.py`, `economy.py`, `usage.py` | LLM cost scales with the **catalog**, not with users; a spend spike has a same-minute kill switch and an always-on meter |
| Queue-based ingestion — Postgres queue, `SKIP LOCKED`, idempotent claims | `ingestion/worker.py` | `docker compose up --scale ingestion-worker=N` is the whole scaling story for parsing throughput |
| Edge rate limit on `/chat` (`RATE_LIMIT_CHAT`) | `api/main.py` | scripted token burn stops at the gateway, before any LLM |
| Data hygiene — session retention TTL, cache TTL purge, bounded ledgers | `agent/retention.py` | tables can't grow without bound; DPA minimization holds at any scale |

## Triggers → next step (in likely firing order)

| Signal you'll actually see | Change to make | Size |
|---|---|---|
| One api/agent container saturates (p95 latency up, CPU pegged) | Run replicas behind the reverse proxy — already safe (stateless, no sticky). Budget `AGENT_DB_POOL_SIZE × replicas` under Postgres `max_connections` (default 100) | config |
| More than one **api** replica | The in-process `/chat` limiter becomes per-replica (N× the intended budget). Move the sliding window to Postgres (one table, same interface) or Redis if one exists by then | small PR |
| Postgres connection pressure (`too many connections`, pool waits) | Put pgbouncer in front (pool kwargs already set `prepare_threshold=0`, safe for transaction pooling); raise/replan pool budgets | infra |
| Ingestion needs a second host, or api/ingestion split hosts | Uploads live on a local Docker volume — move `DOCS_DIR` to S3-compatible object storage behind the existing storage seam in `ingestion/` (protocol trigger per CLAUDE.md) | medium PR |
| Queue latency: uploads sit `queued` for minutes | `--scale ingestion-worker=N` (already supported, `SKIP LOCKED` is safe) | config |
| Read latency on catalog queries as the catalog grows (thousands of policies) | pgvector index tuning (HNSW/IVFFlat) + `search_policies` pagination; consider a persistent MCP session instead of per-call handshakes | small PR |
| Daily token spend trends toward budget | `LLM_ECONOMY=lean` (drop panel) or `deterministic` (zero LLM) — already live; the `DAILY_TOKEN_BUDGET` warning names the moment | config |
| Checkpoint table growth outpaces retention | Lower `SESSION_TTL_DAYS`; retention is already hourly and fail-safe | config |
| Multi-instance observability gets blurry | Ship container logs to a collector; scrape `GET /ops/usage` per agent instance and sum (rows are per-day upserts — summing instances is correct only if they share one Postgres, which they do) | infra |

## Deliberate non-goals until a trigger fires

- **No Kubernetes / service mesh** — compose + replicas on one or two hosts carries this workload far past 10k monthly users; concurrency, not user count, is the real limit, and a PH insurance suggester's concurrent-chat peak is a tiny fraction of its user base.
- **No Redis / message broker** — Postgres is the queue (ingestion), the cache (explanations), the limiter's future home, and the ledger. One database to operate, back up, and reason about. Add a second datastore only when Postgres measurably can't hold a specific load.
- **No microservice split** — the monorepo/monolith boundary decision is already in CLAUDE.md: split on a concrete trigger.
- **No CDN/edge cache for the PWA** — nginx serves static files; a CDN is a one-line DNS change later, not architecture.

The common thread: everything user-facing is already stateless-over-Postgres,
so every scaling move above is *additive* (replicas, poolers, object storage) —
none requires rewriting a flow that works today.
