# Git & commits

## Principle

Leave a clean, honest history. Commits are for the next reader (often you):
each one should explain *why*, group related work, and be safe to act on.

## Workflow

- The assistant **commits locally**; the owner **pushes** — unless the owner asks
  the assistant to push. Don't push to a shared branch on your own initiative.
- If you're on the default branch and the work warrants isolation, branch first.
- Never commit or push work you haven't lint-checked and tested (see
  `testing-verification.md`).

## Commit messages

- Imperative subject line, scoped and specific ("Add durable queue worker", not
  "updates").
- Body explains **why** and **what changed**, and **how it was verified** — the
  reasoning that won't be obvious from the diff.
- Attribute co-authorship when pairing (`Co-Authored-By: ...`).

## Squashing

When asked to squash a batch of session commits into one:

```bash
git reset --soft <base-sha>          # base = last commit you want to keep
git commit -F - <<'EOF'
<comprehensive message covering the whole batch>
EOF
git diff <old-head> HEAD --stat      # MUST be empty — proves the tree is unchanged
git push --force-with-lease origin <branch>
```

- Always verify `git diff <old-head> HEAD` is empty before force-pushing — the
  squash must preserve the exact tree, only collapse history.
- Use `--force-with-lease` (never a bare `--force`) so a concurrent update aborts
  the push instead of being clobbered.
- Only squash your own unshared/short-lived history, and only when asked.

## Hygiene

- After dependency changes, re-lock and commit the lockfile in the same change.
- Keep secrets and build cruft out of commits *and* out of build context — a
  missing `.dockerignore`/`.gitignore` entry leaks the local virtualenv or `.env`
  into images/history. If a secret ever lands somewhere shared, rotate it; don't
  just delete it.

**On this project:** end commit bodies with the `Co-Authored-By` trailer; after
`pyproject.toml` changes run `uv lock` before pushing (CI uses `--locked`).
