"""Version resolution: one number for /health, the PWA footer, the image tag,
and the git tag. Getting this wrong means a deployment reports a version it
isn't, so the precedence and the never-lie fallback are pinned here."""

from pathlib import Path

from shared.version import BUILD_FALLBACK, FALLBACK

from shared import app_version, build_id

REPO = Path(__file__).resolve().parents[2]


def test_env_override_wins(monkeypatch) -> None:
    # Compose passes APP_VERSION=$IMAGE_TAG, so a pinned deploy reports the
    # release it was deployed as, whatever the image happens to have baked in.
    monkeypatch.setenv("APP_VERSION", "9.9.9")
    monkeypatch.delenv("BUILD_ID", raising=False)  # even with no build stamp...
    app_version.cache_clear()
    build_id.cache_clear()
    assert app_version() == "9.9.9"  # ...an explicit override is never suffixed
    app_version.cache_clear()
    build_id.cache_clear()


def test_unpublished_build_is_marked_dev(monkeypatch) -> None:
    """A source checkout has no BUILD_ID, so it is not a published artifact. It
    must NOT report the committed VERSION bare: that file is the release FLOOR
    (deliberately left behind as tags advance), so "0.1.1" would claim to be a
    real past release while the build stamp said "dev"."""
    monkeypatch.delenv("APP_VERSION", raising=False)
    monkeypatch.delenv("BUILD_ID", raising=False)
    app_version.cache_clear()
    build_id.cache_clear()
    floor = (REPO / "VERSION").read_text().strip()
    assert app_version() == f"{floor}+dev"
    app_version.cache_clear()
    build_id.cache_clear()


def test_ci_built_artifact_reports_the_bare_version(monkeypatch) -> None:
    """CI writes a BUILD_ID beside VERSION for every image it publishes — that
    is what proves this is a real release, so no +dev suffix."""
    monkeypatch.delenv("APP_VERSION", raising=False)
    monkeypatch.setenv("BUILD_ID", "202607271200")
    app_version.cache_clear()
    build_id.cache_clear()
    assert app_version() == (REPO / "VERSION").read_text().strip()
    app_version.cache_clear()
    build_id.cache_clear()


def test_blank_env_is_ignored(monkeypatch) -> None:
    # compose renders APP_VERSION as "" when IMAGE_TAG is unset — that must not
    # blank out the version (it falls through to the file, marked unpublished).
    monkeypatch.setenv("APP_VERSION", "   ")
    monkeypatch.delenv("BUILD_ID", raising=False)
    app_version.cache_clear()
    build_id.cache_clear()
    assert app_version() == (REPO / "VERSION").read_text().strip() + "+dev"
    app_version.cache_clear()
    build_id.cache_clear()


def test_fallback_is_obviously_unreleased() -> None:
    # Never invent a plausible version: an unstamped build must be identifiable.
    assert FALLBACK.endswith("+dev")


def test_version_file_is_a_release_number() -> None:
    text = (REPO / "VERSION").read_text().strip()
    major, minor, patch = text.split(".")
    assert all(part.isdigit() for part in (major, minor, patch)), text


def test_release_floor_is_not_below_the_workspace_version() -> None:
    # VERSION is the source of truth; the per-package pyproject versions are
    # inert (nothing is published to PyPI). This guards the one thing that
    # matters: the floor never regresses below where the packages claim to be.
    floor = tuple(int(p) for p in (REPO / "VERSION").read_text().strip().split("."))
    pyproject = (REPO / "pyproject.toml").read_text()
    declared = next(
        line.split("=")[1].strip().strip('"')
        for line in pyproject.splitlines()
        if line.startswith("version = ")
    )
    assert floor >= tuple(int(p) for p in declared.split("."))


def test_build_id_env_override_wins(monkeypatch) -> None:
    monkeypatch.setenv("BUILD_ID", "202607271200")
    build_id.cache_clear()
    assert build_id() == "202607271200"
    build_id.cache_clear()


def test_build_id_falls_back_to_dev_in_a_checkout(monkeypatch) -> None:
    # BUILD_ID is written into the build context by CI and gitignored, so a
    # source checkout has none — it must say "dev", never fake a build stamp.
    monkeypatch.delenv("BUILD_ID", raising=False)
    build_id.cache_clear()
    assert build_id() == BUILD_FALLBACK == "dev"
    build_id.cache_clear()
