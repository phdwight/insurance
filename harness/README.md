# Engineering harness

Reusable working agreements — distilled from practice, written to be portable.
Drop this folder into any repo; the principles are project-agnostic and each
file calls out "**On this project**" where the specifics differ.

**This is a living harness.** When a session surfaces a valuable, reusable
lesson — a convention, a workflow that worked, a gotcha worth not
rediscovering — add it to the relevant file (or a new one) and update this
index, as part of the work.

## Files

| File | What it governs |
|---|---|
| [code-design.md](code-design.md) | SOLID / DRY / clean code — and *cohesion over ceremony* (abstractions on trigger, not speculatively) |
| [diagrams-drawio.md](diagrams-drawio.md) | Authoring `.drawio` diagrams and the render-and-verify loop |
| [docs-in-sync.md](docs-in-sync.md) | Docs + diagram + implementation + tests move together |
| [testing-verification.md](testing-verification.md) | Functional cross-layer tests; verify by driving the real flow |
| [background-jobs.md](background-jobs.md) | Durable work off the request path — DB-backed queue + worker, not in-process tasks |
| [deploy-gotchas.md](deploy-gotchas.md) | Secure-context APIs, proxy timeouts, image bloat/secrets, ML wheel matching |
| [git-commits.md](git-commits.md) | Branch / commit / squash / push and message style |

## How to use it

- **This project** — the authoritative, project-specific rules live in the repo
  root `CLAUDE.md` (decision log, stack, seams). This harness is the *portable
  distillation of the working style*; where the two overlap, `CLAUDE.md` wins
  for anything project-specific.
- **A new project** — copy `harness/` in, delete the "On this project" notes (or
  replace them with the new project's specifics), and seed its `CLAUDE.md` from
  the general principles here.
- **Globally** — to apply the general principles to *every* project without
  copying, lift the non-project parts into `~/.claude/CLAUDE.md` (loaded in every
  session). Keep it short there; link back to these files for detail.

## The one-line version

Build the simplest thing that fits; prove it works by exercising it; keep the
docs, diagrams, and tests telling the same true story as the code; and leave a
clean, honest trail in git.
