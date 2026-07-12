# LangGraph Agent Design

Diagram: [`agent-graph.drawio`](agent-graph.drawio) (kept in sync with the implementation).

## Goal

One graph serves both intake modes. Free-form chat extracts a **NeedsProfile** from natural language; guided mode fills the same profile via a questionnaire. Everything downstream (matching, ranking, explaining) is shared.

## State

```python
class NeedsProfile(TypedDict):
    product_lines: list[str]          # detected: ["life", "travel", ...]
    demographics: dict                # age, dependents, location, occupation
    budget: dict                      # amount, frequency, currency (PHP)
    per_line_details: dict            # line-specific fields, e.g. travel.destinations
    risk_notes: list[str]             # smoker, pre-existing conditions (sensitive!)

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    mode: Literal["freeform", "guided"]
    profile: NeedsProfile
    candidates: dict[str, list]       # per line: full policy records, narrowed
    recommendations: dict[str, list]  # per line: verified + explained
    pending_disc: str | None          # discriminator being asked
    asked: list[str]                  # discriminators already used
    questions_asked: int              # question budget tracking
```

Checkpointed to Postgres (LangGraph checkpointer) so sessions survive refreshes — important for a PWA.

## Graph — catalog-driven elicitation

There is **no static intake form**. Questions exist only because the current
candidate policies disagree on an attribute; the customer's answers narrow the
candidate set until a match (or an honest no-match) falls out.

```
 user msg ─▶ ingest ─┬─▶ ask_bootstrap ─▶ END(turn)     (no product line yet;
                     │        │ MCP: list_product_lines — offers only lines
                     │        │ with published policies, static fallback)
                     ▼
                   match      ── MCP: search_policies + get_policy (full records,
                     │            parallel per detected line)
                     ▼
                   decide     ── narrow candidates by answers so far, then pick
                     │           the question that best SPLITS what remains
        question ◀───┴───▶ finalize
           │                   │
           ▼                   ▼
    ask_question ─▶ END     verify ─▶ explain ─▶ verify_explanations ─▶ present
    (next turn loops           (programmatic     (multi-LLM panel)
     back into ingest)          guardrail)
```

### Node notes

**ask_bootstrap.** Catalog-first even before a line is chosen: options come live from MCP `list_product_lines`, filtered to lines with published policies (a line with zero policies is never offered), with a static fallback only if the catalog is unreachable. Capped at 3 attempts (see guardrails).

**ingest.** Updates the profile from the user's message. Guided mode parses the pending question's answer deterministically (each discriminator owns its parser — works with zero LLM keys); free-form mode adds structured-output LLM extraction merged non-destructively. Fabricating values is the main failure mode — the prompt requires `null` over guesses.

**match.** Runs *early*, with whatever partial profile exists — the catalog is consulted before questions are chosen, not after. Fetches full policy records per detected line in parallel.

**decide (discriminator engine).** Deterministic, no LLM. Narrows candidates by every answer given so far (destination region, trip length, species, plan type, age band…), then scores each unanswered attribute by how evenly it splits the remaining candidates. The best splitter becomes the next question. Attributes all candidates agree on are never asked (if every travel policy covers COVID, the COVID question is pointless). Stops when a line is at ≤ 3 candidates, no discriminating attribute remains, or the question budget (5) is spent. Budget is the last-resort question since price always differs. An empty candidate set after narrowing is presented as an honest no-match — never a forced fit.

**verify.** Guardrail node. Programmatically re-checks age eligibility and budget (normalized across premium frequencies) against actual policy fields. This is the anti-hallucination layer for *policy selection*.

**explain.** Generates comparisons grounded ONLY in verified fields; every claim must reference an attribute. Includes disclaimers + "as of" freshness.

**verify_explanations (multi-LLM panel).** After `explain`, a panel of judge models — configured via `VERIFIER_MODELS`, at least two, ideally from different providers than the writer — independently fact-checks each match reason against the policy's verified fields. A reason survives only on a unanimous "grounded" vote; failed reasons are dropped silently (a policy whose reasons all fail gets a generic fallback line — the panel never removes a policy, since `rank_and_verify` already validated it). A judge error counts as a rejection, and the whole node is a no-op when fewer than two judges are configured, so the panel can only ever make output stricter, never break it.

**present.** Emits JSON the PWA renders natively (cards, compare matrix) — not a wall of markdown.

## Anti-loop guardrails

Four independent bounds guarantee no session can recurse or interrogate forever: the discriminator loop is capped at 5 questions (`MAX_QUESTIONS`) and never repeats an asked attribute; the bootstrap question is capped at 3 attempts before politely ending the session (`MAX_BOOTSTRAP_TURNS`); an absolute 20-turn ceiling forces finalization regardless of state (`MAX_TURNS`); and each single invocation runs under LangGraph's `recursion_limit=15`, so a graph wiring bug fails fast instead of spinning.

## Conversation policies

- Max one clarifying question per turn in free-form mode (differentiator: don't recreate the questionnaire).
- Sensitive data (health conditions): collect only what's needed for matching, flag in state, honor deletion.
- Off-topic/unsafe input: polite redirect node (implicit via system prompt + router).
- Always allow "just show me something" → proceed with defaults.

## Evaluation plan

- Golden set of ~50 synthetic user descriptions → expected profile extractions (measure field precision/recall).
- Grounding check: automated test that every attribute mentioned in explanations exists in the cited policy version.
- Trace review in LangSmith/Langfuse weekly during development.
