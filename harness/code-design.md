# Code design — SOLID, DRY, and cohesion over ceremony

## Principle

Follow SOLID and DRY, but **cohesion over ceremony**: the goal is code that is
easy to change and easy to read, not the maximum number of layers. A pattern
you don't need yet is a cost, not an investment.

## Abstractions on trigger, not speculatively

Introduce an interface / `Protocol` / base class **only when a concrete second
case appears** — a real second implementation, a real second caller with
different needs, a real extension point someone is about to build. Until then:

- Keep functions flat and modules concrete.
- Use **module-level seams** for testing (import a function, monkeypatch it) —
  you do not need dependency-injection scaffolding to make code testable.
- When the trigger *does* arrive, introduce the seam at that boundary and name
  it after the real thing it abstracts.

Ask before adding a layer: *what concrete thing forces this abstraction today?*
If the answer is "it might be useful later," don't.

**On this project:** the trigger rules are explicit in `CLAUDE.md` — e.g. a
second catalog source → a `CatalogClient` protocol; a model provider beyond
`init_chat_model` strings → an `LLMProvider` protocol. Until a trigger fires,
functions stay flat and tests patch the module seams.

## DRY without over-DRYing

- One source of truth for shared config and constants. Derive, don't duplicate
  (e.g. build a connection URL from its parts; a compose file uses YAML anchors
  for shared env/logging blocks rather than repeating them).
- Don't hoist two similar-looking things into one abstraction until they've
  proven they change together. Duplication is cheaper than the wrong abstraction.

## Clean-code habits that paid off

- **Centralize what shouldn't be inline** — prompts, user-facing copy, and
  structured-output contracts live in one place, never scattered through logic.
- **Fail loud, not silent** — a fallback (a slower parser, a skipped optional
  step) carries its reason into the output/logs and the UI; never downgrade
  quality quietly.
- **Match the surrounding code** — naming, comment density, and idiom should
  read as if one person wrote the file.
- **Small, honest units** — a function does one thing; a comment explains *why*,
  not *what*.
