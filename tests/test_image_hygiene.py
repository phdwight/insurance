"""Repo-level image hygiene: the published images must never carry secrets or
dev-only baggage.

This is a real regression guard, not a style check: these packages are PUBLIC
on GHCR, and a local `deploy/push-images.sh` run sends the working tree (which
DOES contain .env) as the build context. Before .dockerignore existed, that
baked live API keys into published images. Docker applies .dockerignore
patterns itself, so we assert the patterns are present rather than shelling out
to a build — this runs in milliseconds on every PR, and push-images.sh does the
belt-and-braces build-context probe at publish time.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOCKERIGNORE = (REPO / ".dockerignore").read_text().splitlines()
PATTERNS = {line.strip() for line in DOCKERIGNORE if line.strip() and not line.startswith("#")}


def test_secrets_are_excluded_from_the_build_context() -> None:
    # .env holds live provider keys, ADMIN_TOKEN and POSTGRES_PASSWORD.
    assert ".env" in PATTERNS
    assert ".env.*" in PATTERNS
    assert "!.env.example" in PATTERNS  # the committed template must survive


def test_heavy_dev_only_paths_are_excluded() -> None:
    # Each of these is dead weight in a runtime image (.venv alone is ~1.3 GB
    # locally; samples is ~2 MB of brochure PDFs).
    for pattern in (".venv", ".git", "pwa", "samples", "docs", "harness", "**/tests"):
        assert pattern in PATTERNS, pattern


def test_uv_cache_is_not_persisted_into_the_image() -> None:
    # UV_LINK_MODE=copy already copies packages into .venv, so uv's download
    # cache is pure bloat in the final layer (~1.4 GB on ingestion). Nothing at
    # runtime reads it, so the sync must run with --no-cache.
    dockerfile = (REPO / "Dockerfile.python").read_text()
    sync = next(line for line in dockerfile.splitlines() if "uv sync" in line)
    assert "--no-cache" in sync


def test_publish_script_refuses_to_ship_a_leaky_context() -> None:
    script = (REPO / "deploy" / "push-images.sh").read_text()
    assert "/ctx/.env" in script  # the preflight probe
    assert "exit 1" in script  # ...and it actually aborts
