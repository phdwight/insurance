"""Version resolution: one number for /health, the PWA footer, the image tag,
and the git tag. Getting this wrong means a deployment reports a version it
isn't, so the precedence and the never-lie fallback are pinned here."""

from pathlib import Path

from shared.version import FALLBACK

from shared import app_version

REPO = Path(__file__).resolve().parents[2]


def test_env_override_wins(monkeypatch) -> None:
    # Compose passes APP_VERSION=$IMAGE_TAG, so a pinned deploy reports the
    # release it was deployed as, whatever the image happens to have baked in.
    monkeypatch.setenv("APP_VERSION", "9.9.9")
    app_version.cache_clear()
    assert app_version() == "9.9.9"
    app_version.cache_clear()


def test_falls_back_to_the_version_file(monkeypatch) -> None:
    monkeypatch.delenv("APP_VERSION", raising=False)
    app_version.cache_clear()
    assert app_version() == (REPO / "VERSION").read_text().strip()
    app_version.cache_clear()


def test_blank_env_is_ignored(monkeypatch) -> None:
    # compose renders APP_VERSION as "" when IMAGE_TAG is unset — that must not
    # blank out the version.
    monkeypatch.setenv("APP_VERSION", "   ")
    app_version.cache_clear()
    assert app_version() == (REPO / "VERSION").read_text().strip()
    app_version.cache_clear()


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
