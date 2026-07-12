# Overview & Vision

## What we're building

A Progressive Web App (PWA) where a user describes their insurance needs — life, health, pet, travel, motor, etc. — and an agentic AI suggests concrete policies that match. The system draws its policy knowledge from a dedicated MCP (Model Context Protocol) server backed by a Postgres database of ingested insurance policies.

**Market:** Philippines (initially).
**Positioning:** Suggest + compare. We present matching policies with plain-language comparisons and explanations. Purchase happens with the insurer or a licensed agent — we do not quote, bind, or sell.

## Differentiation

1. **Free-form agentic intake.** Instead of a rigid turn-by-turn questionnaire, the user writes (or speaks) freely: *"I'm 34, two kids, freelance, I travel to Japan twice a year, and my dog is getting old."* The agent extracts needs, asks only for what's missing, and recommends. Traditional guided Q&A remains available as an opt-in mode.
2. **MCP-based policy layer.** Policy data lives behind an MCP server, cleanly decoupled from the app. Any agent (ours or third-party) can query it. This makes the policy catalog a product in itself.
3. **Multi-line coverage in one conversation.** One intake can surface life + travel + pet needs simultaneously, rather than siloed per-product flows.

## Two-part system

| Part | Purpose |
|---|---|
| **Policy Platform** | Ingest policy documents from insurers/agents, normalize into a structured catalog in Postgres, expose via MCP server |
| **Customer App** | PWA chat/guided interface → LangGraph agent → MCP queries → recommendation & comparison results |

## Tech stack

- **Postgres** — policy catalog, user sessions, conversation state, vector search (pgvector)
- **LangGraph** — agent orchestration (intake, extraction, matching, explanation)
- **PWA** — installable, offline-tolerant web frontend
- **MCP** — protocol boundary between the agent and the policy catalog

## Scope

### In scope (MVP)
- Free-form and guided intake for 4 lines: life, health, travel, pet
- Policy ingestion via manual/document upload (PDF brochures, policy summaries) with LLM-assisted extraction and human review
- Recommendation results: ranked policies, side-by-side comparison, "why this matches" explanations
- MCP server with search/filter/detail tools over the catalog

### Out of scope (MVP)
- Purchase, quoting, binding, payments
- Insurer API integrations (later phase)
- Agent/lead-gen marketplace (possible later phase)
- Claims assistance

## Regulatory & compliance notes (Philippines)

> Not legal advice — validate with counsel before launch.

- **Insurance Commission (IC):** Selling or soliciting insurance requires licensing. Presenting comparative information without soliciting keeps us closer to an "information service," but the line matters — wording of recommendations must avoid solicitation. If we later add lead-gen or purchase, IC licensing (broker/agent) becomes a hard requirement.
- **Data Privacy Act of 2012 (RA 10173):** Intake collects sensitive personal information (health conditions, age, dependents). Requires: consent capture, privacy notice, NPC registration if thresholds met, breach procedures, data minimization.
- **Disclaimers:** Every recommendation must state it is informational, not financial/insurance advice, and that final terms come from the insurer.
- **Accuracy liability:** Ingested policy data can go stale. Show "as of" dates, link to official insurer documents, and version the catalog.

## Success criteria (MVP)

- User can go from free-text description to ranked recommendations in under 3 minutes
- ≥ 90% of catalog entries pass human review without correction after extraction tuning
- Recommendation explanations cite actual policy attributes (no hallucinated coverage)
