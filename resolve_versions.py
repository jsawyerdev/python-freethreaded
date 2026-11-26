"""Resolve the newest GCC image and the newest CPython patch of each tracked minor version.

Both CI pipelines run this before building so every scheduled build uses the latest
upstream releases without hand-edited pins. It only reads public upstream metadata:

- GCC: the official-images manifest for the Docker Hub `gcc` image, whose `Tags:` lines
  list every currently maintained `X.Y.Z` tag.
- CPython: python.org's release API, which publishes the SHA256 of each source tarball;
  the Dockerfile verifies the downloaded tarball against it.

Exits non-zero if any upstream lookup fails or a tracked minor has no stable release.
"""

import argparse
import json
import logging
import re
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterable
from typing import Any

logger = logging.getLogger("resolve_versions")

# Minor versions to publish, newest first. Adding or removing one is a deliberate decision
# (free-threading support differs per minor), so it is not discovered automatically.
PYTHON_MINORS = ("3.15", "3.14")

GCC_LIBRARY_URL = "https://raw.githubusercontent.com/docker-library/official-images/master/library/gcc"
PYTHON_RELEASES_URL = (
    "https://www.python.org/api/v2/downloads/release/?is_published=true"
)
# os/3 is "Source release" in python.org's download API.
PYTHON_SOURCE_FILES_URL = "https://www.python.org/api/v2/downloads/release_file/?os=3"

FETCH_ATTEMPTS = 3
FETCH_TIMEOUT_SECONDS = 30

Version = tuple[int, int, int]

_GCC_TAG = re.compile(r"(\d+)\.(\d+)\.(\d+)")
_PYTHON_RELEASE_NAME = re.compile(r"Python (\d+)\.(\d+)\.(\d+)")
_SHA256 = re.compile(r"[0-9a-f]{64}")


def fetch(url: str) -> bytes:
    """GET a URL, retrying transient network failures a bounded number of times."""
    for attempt in range(1, FETCH_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(url, timeout=FETCH_TIMEOUT_SECONDS) as response:
                data: bytes = response.read()
                return data
        except (urllib.error.URLError, TimeoutError) as exc:
            # 4xx responses will not fix themselves; fail immediately.
            if isinstance(exc, urllib.error.HTTPError) and exc.code < 500:
                raise
            if attempt == FETCH_ATTEMPTS:
                raise
            logger.warning("fetch %s failed (attempt %d): %s", url, attempt, exc)
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def format_version(version: Version) -> str:
    return ".".join(map(str, version))


def newest_gcc(library: str) -> str:
    """Return the highest `X.Y.Z` tag listed in the official-images `gcc` manifest."""
    versions: list[Version] = []
    for line in library.splitlines():
        key, sep, value = line.partition(":")
        if not sep or key.strip() != "Tags":
            continue
        for tag in value.split(","):
            match = _GCC_TAG.fullmatch(tag.strip())
            if match:
                versions.append((int(match[1]), int(match[2]), int(match[3])))
    if not versions:
        raise SystemExit("no X.Y.Z tags found in the gcc official-images manifest")
    return format_version(max(versions))


def newest_pythons(
    releases: Iterable[dict[str, Any]], minors: Iterable[str]
) -> dict[str, tuple[str, str]]:
    """Map each minor to (newest stable patch version, its release API URI)."""
    newest: dict[str, tuple[Version, str]] = {}
    for release in releases:
        match = _PYTHON_RELEASE_NAME.fullmatch(release["name"])
        if not match or release["pre_release"] or not release["is_published"]:
            continue
        version = (int(match[1]), int(match[2]), int(match[3]))
        minor = f"{version[0]}.{version[1]}"
        if minor not in newest or version > newest[minor][0]:
            newest[minor] = (version, release["resource_uri"])
    resolved: dict[str, tuple[str, str]] = {}
    for minor in minors:
        if minor not in newest:
            raise SystemExit(f"python.org lists no stable release for Python {minor}")
        version, uri = newest[minor]
        resolved[minor] = (format_version(version), uri)
    return resolved


def tarball_sha256(
    files: Iterable[dict[str, Any]], version: str, release_uri: str
) -> str:
    """Return the published SHA256 of Python-<version>.tar.xz for the given release."""
    filename = f"/Python-{version}.tar.xz"
    for file in files:
        if file["release"] == release_uri and file["url"].endswith(filename):
            sha256: str = file["sha256_sum"]
            if not _SHA256.fullmatch(sha256):
                raise SystemExit(
                    f"python.org has no valid SHA256 for {filename}: {sha256!r}"
                )
            return sha256
    raise SystemExit(f"python.org lists no {filename} for release {release_uri}")


def resolve(minors: Iterable[str]) -> dict[str, Any]:
    gcc = newest_gcc(fetch(GCC_LIBRARY_URL).decode("utf-8"))
    pythons = newest_pythons(json.loads(fetch(PYTHON_RELEASES_URL)), minors)
    files = json.loads(fetch(PYTHON_SOURCE_FILES_URL))
    return {
        "gcc": gcc,
        "pythons": [
            {
                "minor": minor,
                "version": version,
                "sha256": tarball_sha256(files, version, uri),
            }
            for minor, (version, uri) in pythons.items()
        ],
    }


def to_env(resolved: dict[str, Any]) -> str:
    """Render as KEY=value lines (GitLab dotenv), e.g. PYTHON_3_15_VERSION=3.15.2."""
    lines = [
        f"GCC_VERSION={resolved['gcc']}",
        f"PYTHON_LATEST_MINOR={resolved['pythons'][0]['minor']}",
    ]
    for python in resolved["pythons"]:
        key = python["minor"].replace(".", "_")
        lines.append(f"PYTHON_{key}_VERSION={python['version']}")
        lines.append(f"PYTHON_{key}_SHA256={python['sha256']}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--format", choices=("json", "env"), default="json")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(name)s: %(message)s", stream=sys.stderr
    )

    resolved = resolve(PYTHON_MINORS)
    logger.info(
        "gcc %s; python %s",
        resolved["gcc"],
        ", ".join(python["version"] for python in resolved["pythons"]),
    )
    if args.format == "json":
        print(json.dumps(resolved, separators=(",", ":")))
    else:
        sys.stdout.write(to_env(resolved))


if __name__ == "__main__":
    main()
