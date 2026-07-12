# Roadmap, Risks & Open Questions

## Phases

### Phase 0 — Foundations (1–2 weeks)
- Repo structure (monorepo: `pwa/`, `api/`, `agent/`, `mcp-server/`, `ingestion/`, `docs/`), Docker Compose, CI
- Postgres with `app` + `catalog` schemas, pgvector enabled
- Pick LLM provider; set up LangSmith/Langfuse tracing
- **Exit:** `docker compose up` runs all service skeletons; migrations apply

### Phase 1 — Catalog & MCP server (2–3 weeks)
- Catalog schema + migrations
- Manually seed 15–20 real PH policies (hand-entered from public brochures) — *don't block on the pipeline to get data*
- MCP server: `list_product_lines`, `list_insurers`, `search_policies`, `get_policy`, `compare_policies`
- Hybrid search (SQL filters + pgvector)
- **Exit:** an MCP client (e.g., Claude Desktop / inspector) can find "travel insurance to Japan under ₱2,000" in the seed data

### Phase 2 — Agent core (2–3 weeks)
- LangGraph graph: extract_needs → gap_check → match → rank_and_verify → explain → present
- Postgres checkpointer; golden-set extraction evals; grounding tests
- **Exit:** CLI/API conversation produces grounded, ranked recommendations from seed catalog

### Phase 3 — PWA MVP (3–4 weeks)
- Intake (free-form), streaming, profile chips, results cards, compare view, detail sheet
- PWA install + offline results snapshot; disclaimers & consent flow
- **Exit:** end-to-end demo on a phone, installable

### Phase 4 — Guided mode + ingestion pipeline (2–3 weeks)
- Questionnaire node + guided UI (shares field-priority tables)
- Upload portal → parse → LLM extraction → review queue → publish
- Backfill catalog to ~50+ policies across 4 lines
- **Exit:** a non-engineer can add a policy from a PDF in < 10 minutes

### Phase 5 — Hardening & soft launch
- Load/perf pass, security review, privacy notice + counsel review, error reporting loop, analytics
- **Session TTL purge:** scheduled job deleting agent checkpoint rows older than ~30 days — Data Privacy Act minimization (checkpoints hold age/budget/risk notes). Not a conversation timeout: turns are stateless between messages by design, and `match` re-fetches the catalog every turn so long-idle sessions can't act on stale policy data.
- **PWA idle nudge (optional):** after a few minutes of inactivity mid-questioning, offer "show best matches with what you've told me so far" (triggers the existing finalize path early)
- Closed beta with real users; iterate on extraction quality and ranking

### Status (as of 2026-07-12)
Phases 0–4 complete: catalog + MCP server (with dynamic, catalog-driven elicitation replacing the planned static gap-check), agent with programmatic guardrail + multi-LLM verifier panel, PWA with chips/SSE/typed questions, and the full ingestion pipeline (docling parsing, LLM extraction with schema sanitization + normalization, reviewer UI at `:8003/admin` covering the "non-engineer adds a policy from a PDF in <10 minutes" exit test).

Phase 5 progress: **done** — ingestion admin auth (`ADMIN_TOKEN`), session TTL purge (`SESSION_TTL_DAYS`, hourly), compare view in the PWA, PWA icons/installability. **Remaining** — replace demo seed with real PH policies (the big one), privacy notice + consent copy with counsel review, deployment to a host, analytics/error-reporting loop, load/perf pass, optional idle nudge.

Rough total: ~3–4 months part-time solo, faster with help. Phases 1–2 can proceed in parallel with 3 if two workstreams exist.

## Top risks & mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Hallucinated coverage claims | Trust-destroying | rank_and_verify guardrail node; human-reviewed catalog; grounding tests in CI |
| Stale policy data | Wrong recommendations | Versioning, `verified_at` surfaced in UI, re-verification job, "report an error" |
| Crossing into solicitation (IC regs) | Legal | Suggest+compare only; no quoting/binding; counsel review of result-page wording before launch |
| Sensitive health data handling | DPA violations | Consent gate, data minimization, deletion support, encrypt at rest |
| Extraction quality on messy PDFs | Slow catalog growth | Human review queue is mandatory; hand-seed first; improve prompts per line iteratively |
| Cold-start catalog (few policies) | Thin recommendations | Seed manually from public brochures; prioritize 2 lines (travel + life) if needed |
| LLM cost/latency in chat | UX + unit economics | Small model for extraction/routing, larger only for explain; cache MCP results per session |

## Open questions (decide before/during Phase 1)

1. **Insurer relationships:** purely public-document ingestion at first, or partner with 1–2 insurers/agencies for verified data? (Partnering improves data + credibility.)
2. **Which 2 lines to nail first** if 4 is too many for MVP? Suggest travel (simple, transactional) + life (high value).
3. **Accounts:** anonymous-only MVP vs. early accounts for saved results? (Anonymous recommended; add accounts when retention matters.)
4. **LLM provider & data residency** for sensitive intake text.
5. **Monetization** (affects positioning): lead-gen fees later? referral links? Keep results unbiased regardless — disclose any compensation.
6. **Name/branding + domain.**

## Document map

| Doc | Contents |
|---|---|
| `00-overview.md` | Vision, differentiation, scope, PH compliance |
| `01-architecture.md` | Components, data flows, stack decisions |
| `02-ingestion-mcp.md` | Pipeline, catalog schema, MCP tools |
| `03-agent-design.md` | LangGraph state, graph, guardrails, evals |
| `04-pwa-ux.md` | Screens, PWA capabilities, streaming protocol |
| `05-roadmap.md` | Phases, risks, open questions |
| `agent-graph.drawio` | LangGraph agent diagram (kept in sync with the graph) |
| `ingestion-pipeline.drawio` | Ingestion pipeline diagram (kept in sync with the flow) |
