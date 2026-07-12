# PWA & UX Plan

## Principles

- **Free-form first, guided always visible.** The hero interaction is a single text box: "Tell us what you want to protect." A "Guide me instead" toggle is one tap away, and switching preserves progress.
- **Results are structured, not chat transcripts.** Recommendations render as cards and comparison tables; chat is the input method, not the output format.
- **Trust surface everywhere:** insurer name, "as of" date, link to official document, and an informational-only disclaimer on every result.

## Screens

1. **Landing / intake** *(built in Phase 3)*
   - Headline "What would you like to protect?" over a free-text box (feeds the LLM extraction path, mode=freeform)
   - Category chips below — **sourced live from MCP `list_product_lines`** with policy counts, so the UI only advertises lines the catalog can actually serve; tapping one starts a guided (deterministic, LLM-free) session
   - Persistent "information only, not insurance advice" disclaimer; no login required (anonymous session id)

2. **Conversation view (free-form)**
   - Streaming agent replies; extracted profile shown as editable chips in a side/top panel ("Age: 34 ✎", "Budget: ₱2,000/mo ✎") so users see and correct what the agent understood — key trust feature
   - At most one clarifying question per turn

3. **Guided flow** *(built in Phase 3 — not a form)*
   - Same chat loop as free-form, but every question is deterministic and catalog-derived: choice questions render as tap chips (Yes/No, regions, species…), numeric questions switch to a numeric input; free typing always remains available; answers narrow the live candidate set until results or an honest no-match

4. **Results**
   - Per product line: ranked policy cards (insurer, name, premium range, top 3 matched benefits, match reasons)
   - "Compare" *(built in Phase 5)* — checkbox 2–4 result cards → aligned attribute table (premiums, eligibility, coverage, exclusions, verified date) from MCP `compare_policies` via the gateway's `/compare`
   - Policy detail sheet: full coverage/exclusions, source doc link, verified date
   - CTA: "Contact insurer" / official product page (no in-app purchase)
   - Share/save: snapshot link (recommendation snapshot table)

5. **Session history** (post-MVP: accounts; MVP: local device via session token)

## PWA specifics

| Capability | Plan |
|---|---|
| Installability | Web manifest, icons (192/512 + maskable + apple-touch, shipped in Phase 5), standalone display |
| Service worker | Cache app shell + static assets (Workbox); network-first for API |
| Offline | Read-only: last results snapshot viewable offline; intake requires network (agent is server-side) — show graceful offline state |
| Push notifications | Post-MVP (e.g., "policy you saved was updated") |
| Performance | Code-split; target < 200KB initial JS; skeleton loaders during agent streaming |

## Frontend stack

- React + Vite + `vite-plugin-pwa` (SPA is fine; SEO needs are minimal for a tool-like app — revisit if content marketing pages needed)
- Tailwind for styling; shadcn/ui components
- SSE client for streaming agent tokens/structured events
- State: TanStack Query + lightweight store (Zustand)

## Streaming protocol (API ⇄ PWA)

Server-sent events with typed events so the UI can render structure mid-conversation:

```
event: token            { text }                      # assistant prose
event: profile_update   { profile }                   # chips panel refresh
event: recommendations  { line, policies[] }          # render cards
event: state            { node, status }              # progress indicator
```

## Accessibility & localization

- WCAG AA targets; full keyboard support in guided mode
- English first; Taglish tolerance in free-form input (the extractor must handle code-switched Filipino/English — include in eval set); Filipino UI localization post-MVP

## Trust & compliance UI

- Persistent footer disclaimer: informational only, not insurance advice
- Consent screen before collecting sensitive info (health), per Data Privacy Act
- "How we ranked these" explainer link on results
- "Report an error" on every policy card (feeds review queue)
