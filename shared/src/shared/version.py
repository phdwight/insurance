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


@lru_cache(maxsize=1)
def app_version() -> str:
    override = os.environ.get("APP_VERSION", "").strip()
    if override:
        return override
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "VERSION"
        if candidate.is_file():
            text = candidate.read_text().strip()
            if text:
                return text
    return FALLBACK
