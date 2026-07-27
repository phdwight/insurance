"""The running version, resolved the same way in every service.

Git tags are the source of truth (CI tags vX.Y.Z on each merge to main); the
committed ``VERSION`` file is the seed for the first release and the floor for a
minor/major bump, and it is what gets baked into an image at build time. Keeping
one resolver means the number in ``/health``, in the PWA footer, in the image
tag, and on the git tag cannot drift apart.

Resolution order:
  1. ``APP_VERSION`` env — an explicit override (CI bakes the released version
     here so a container reports it even if the file is stale),
  2. the nearest ``VERSION`` file walking up from this module — the repo root in
     a checkout, ``/app/VERSION`` inside an image,
  3. ``0.0.0+dev`` — an obviously-unreleased marker, never a plausible-looking
     version that could be mistaken for a real release.
"""

import os
from functools import lru_cache
from pathlib import Path

FALLBACK = "0.0.0+dev"
BUILD_FALLBACK = "dev"


def _stamp(env_var: str, filename: str, fallback: str) -> str:
    override = os.environ.get(env_var, "").strip()
    if override:
        return override
    for parent in Path(__file__).resolve().parents:
        candidate = parent / filename
        if candidate.is_file():
            text = candidate.read_text().strip()
            if text:
                return text
    return fallback


@lru_cache(maxsize=1)
def app_version() -> str:
    return _stamp("APP_VERSION", "VERSION", FALLBACK)


@lru_cache(maxsize=1)
def build_id() -> str:
    """When this image was built — UTC YYYYMMDDHHmm, matching the PWA's stamp.

    Written into the build context by CI (never computed in a Dockerfile RUN:
    Docker caches by command string, so a `date` there would silently bake a
    stale stamp). A source checkout has no BUILD_ID file, so local runs report
    "dev" rather than pretending to be a published build."""
    return _stamp("BUILD_ID", "BUILD_ID", BUILD_FALLBACK)
