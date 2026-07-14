# Documentation in sync with the code

## Principle

**Documentation, diagrams, implementation, and tests move together — in the same
commit.** There should never be a moment where what's documented, what's drawn,
what's built, and what's tested disagree. Stale docs are actively misleading:
they cost more than no docs.

## What this means in practice

- Change a flow or an interface → in the *same commit*, update the code, the
  test that exercises it, the doc that describes it, and the diagram that draws
  it. If you can't update all four, the change isn't done.
- Treat a doc claim as a promise the code must keep. If the code no longer keeps
  it, the doc is a bug.

## The staleness sweep

After a change, grep the docs for things that drift silently. A quick,
repeatable pass catches most of it:

```bash
# adjust the patterns to your project's vocabulary
grep -rniE "phase [0-9]|not yet|TODO|synchronous|background task|<old-port>|<removed-file>|localhost:<old>" \
  README.md docs/*.md
```

Look specifically for:

- **Status claims** that outran reality ("Phase 1 built", "not yet
  implemented").
- **Removed files / renamed things** still referenced.
- **Ports, URLs, service names** that changed.
- **Sync-vs-async / removed-vs-added** wording after a behavior change.

## README is a living surface

Keep the README's status, quick-start, deployment, env/keys, and troubleshooting
sections current — they're the first thing a new reader trusts. When you fix a
class of problem in code, add the matching troubleshooting entry.

**On this project:** `CLAUDE.md` states this as process ("no inconsistencies
between what's documented, drawn, implemented, and tested"). The doc set is
`README.md` + `docs/00..05` + the `docs/*.drawio` diagrams.
