# Deployment gotchas

Hard-won lessons that "worked on my machine" hides. Check these before blaming
the app.

## Secure-context-only browser APIs

Some browser APIs exist **only in a secure context** — HTTPS, or
`http://localhost` / `127.0.0.1`. Over plain HTTP to a LAN IP or bare hostname
they are `undefined` and throw:

- `crypto.randomUUID()`, `crypto.subtle` (WebCrypto)
- **Service workers** won't register (so a PWA isn't installable / offline over
  plain-HTTP LAN)

Symptom: works at `localhost`, blank screen or thrown error at
`http://192.168.x.x`. Fix: feature-detect and fall back (`crypto.getRandomValues`
*does* work in insecure contexts), or serve over HTTPS. Don't assume localhost
behavior generalizes to a LAN/served deployment.

Related: **`window.prompt()` / `alert()` / `confirm()` are not reliable** — many
browsers and embedded webviews block them ("prompt() is not supported"). Don't
gate a real flow (e.g. entering an admin token) behind them; use an inline input
in the page instead.

## Reverse-proxy / edge timeouts

Proxies cap how long a single request may take (e.g. Cloudflare's free edge
~100s → 524). A synchronous endpoint that parses/OCRs/generates for longer than
that gets killed even though the server is still working. Fix: move long work off
the request path (see `background-jobs.md`) so the request returns fast and the
client polls. Bypassing the proxy (hitting the LAN address directly) sidesteps
the limit for internal/admin use.

## Don't bake bloat or secrets into images

`COPY . .` with no `.dockerignore` bakes the local virtualenv, `node_modules`,
`.git`, caches, **and `.env`** into every image layer — even if a later step
overwrites them, the fat/secret layer persists and ships. Symptoms: multi-GB
images; secrets readable in a public registry image. Fix: a `.dockerignore` from
day one (`.venv`, `**/node_modules`, `.git`, caches, `.env*` except
`.env.example`). If a secret ever shipped, **rotate it** — deleting the tag
doesn't unpublish the layer.

## Match native/ML wheels to the target

CPU-only ML stacks break when paired components come from different build
channels. Example: `torch` pinned to the PyTorch CPU index but `torchvision`
resolved from PyPI (CUDA-built) → `RuntimeError: operator torchvision::nms does
not exist` at import. Fix: pin *every* paired package to the same index/build
(and as a direct dep so the pin takes effect). Pre-bake models the app downloads
at first use so the first real request doesn't fetch mid-flight (and it works
offline).

## CI image publishing (multi-arch, GHCR)

- **Build arm64 on native runners, not QEMU.** Emulating an arm64 build of a
  heavy image (torch/docling, large native deps) under QEMU is slow and flaky —
  it can take an hour or OOM. If your registry needs arm64 (e.g. an ARM NAS
  target), build each arch on its own native runner (public GitHub repos get
  free `ubuntu-*-arm` runners), push per-arch by digest, then merge into one
  manifest list. Reliable and fast; no emulation.
- **GITHUB_TOKEN can't always push to a pre-existing package.** A package first
  pushed by a user PAT won't accept the workflow's `GITHUB_TOKEN` until the
  package grants the repo write access (package → Manage Actions access → add the
  repo, Write). New packages the workflow creates are linked automatically.
- **Only rebuild on image-affecting changes.** Gate the workflow with a `paths:`
  filter (source, Dockerfiles, dependency/lock files) so a docs/diagram/compose
  commit doesn't burn a full multi-arch build. Same "what goes in an image" list
  as above.

## Health checks and localhost inside containers

A container healthcheck hitting `http://localhost:PORT` can fail if the server
binds IPv4-only while `localhost` resolves to IPv6 `::1` first — use
`127.0.0.1`. Also: an intentionally-exited init/one-shot container can make some
dashboards flag the whole project as errored; if that matters, make it idle
healthy and gate dependents on `service_healthy`.

**On this project:** production is `docker-compose.prod.yml` (registry images,
host ports from 41500, hardened); the PWA is a static nginx build with the API
URL injected at container start; ingestion parsing runs in a worker to stay under
proxy timeouts. Deployed to a UGREEN NAS behind a Cloudflare tunnel — all four
gotchas above showed up there.
