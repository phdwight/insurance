"""The running version, resolved the same way in every service.

Git tags are the source of truth (CI tags vX.Y.Z on each merge to main); the
committed ``VERSION`` file is the seed for the first release and the floor for a
minor/major bump, and it is what gets baked into an image at build time. Keeping
one resolver means the number in ``/health``, in the PWA footer, in the image
tag, and on the git tag cannot drift apart.

Resolution order:
  1. ``APP_VERSION`` env — an explicit override (prod compose passes
     ``$IMAGE_TAG``, so a pinned deploy reports the release it was deployed as),
  2. the nearest ``VERSION`` file walking up from this module — the repo root in
     a checkout, ``/app/VERSION`` inside an image,
  3. ``0.0.0+dev`` — an obviously-unreleased marker.

A ``+dev`` suffix is added whenever this is NOT a published artifact, which is
detected by the absence of a ``BUILD_ID`` (CI writes one into the build context
for every image it publishes; a source checkout has none). Without that, a local
build inherits the committed ``VERSION`` — the release FLOOR, not the current
version — and reports something like "0.1.1", claiming to be a real past release
while its build stamp says "dev". The floor is deliberately left behind as tags
advance, so that mismatch is permanent and only grows.
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
    version = _stamp("APP_VERSION", "VERSION", FALLBACK)
    # An explicit APP_VERSION is a deliberate statement ("deployed as X"), and
    # the bare fallback is already marked — everything else is only a release if
    # CI built it, which is exactly what a BUILD_ID proves.
    if os.environ.get("APP_VERSION", "").strip() or version == FALLBACK:
        return version
    return version if build_id() != BUILD_FALLBACK else f"{version}+dev"


@lru_cache(maxsize=1)
def build_id() -> str:
    """When this image was built — UTC YYYYMMDDHHmm, matching the PWA's stamp.

    Written into the build context by CI (never computed in a Dockerfile RUN:
    Docker caches by command string, so a `date` there would silently bake a
    stale stamp). A source checkout has no BUILD_ID file, so local runs report
    "dev" rather than pretending to be a published build."""
    return _stamp("BUILD_ID", "BUILD_ID", BUILD_FALLBACK)
