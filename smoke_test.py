"""Verify a free-threaded CPython image was built and assembled as intended.

Runs as a build gate inside the Dockerfile and again in CI to report what was built.
Exits non-zero on the first failed check.
"""

import argparse
import importlib
import logging
import platform
import shutil
import ssl
import subprocess
import sys
import sysconfig
from pathlib import Path

logger = logging.getLogger("smoke_test")


def read_os_release() -> dict[str, str]:
    """Return /etc/os-release as a key/value mapping with quotes stripped."""
    fields: dict[str, str] = {}
    for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep:
            fields[key] = value.strip('"')
    return fields


def check_compiler(expected_prefix: str) -> None:
    compiler = platform.python_compiler()
    if not compiler.startswith(expected_prefix):
        raise SystemExit(
            f"compiler is {compiler!r}, expected prefix {expected_prefix!r}"
        )
    logger.info("compiler: %s", compiler)


def check_free_threading() -> None:
    if sysconfig.get_config_var("Py_GIL_DISABLED") != 1:
        raise SystemExit("Py_GIL_DISABLED is not set: not a free-threaded build")
    if sys._is_gil_enabled():
        raise SystemExit("GIL is enabled at runtime")
    logger.info("free-threading: Py_GIL_DISABLED=1, GIL disabled at runtime")


def check_os(expected_version: str) -> None:
    os_release = read_os_release()
    if os_release.get("VERSION_ID") != expected_version:
        raise SystemExit(
            f"os VERSION_ID is {os_release.get('VERSION_ID')!r}, expected {expected_version!r}"
        )
    logger.info("os: %s", os_release.get("PRETTY_NAME"))


def check_extension_modules() -> None:
    """Import every compiled stdlib extension so missing libraries or symbols surface now."""
    lib_dynload = Path(sysconfig.get_path("platstdlib")) / "lib-dynload"
    names = sorted(path.name.split(".", 1)[0] for path in lib_dynload.glob("*.so"))
    if not names:
        raise SystemExit(f"no extension modules found in {lib_dynload}")
    failures: list[str] = []
    for name in names:
        try:
            importlib.import_module(name)
        except ImportError as exc:
            failures.append(f"{name}: {exc}")
    if failures:
        raise SystemExit("extension modules failed to import:\n" + "\n".join(failures))
    logger.info("extension modules: %d imported", len(names))


def check_tls_trust_store() -> None:
    ca_count = ssl.create_default_context().cert_store_stats()["x509_ca"]
    if ca_count == 0:
        raise SystemExit("TLS trust store is empty: ca-certificates missing")
    logger.info("tls: %s, %d CA certificates", ssl.OPENSSL_VERSION, ca_count)


def check_pip() -> None:
    pip = shutil.which("pip3")
    if pip is None:
        raise SystemExit("pip3 is not on PATH")
    result = subprocess.run(
        [pip, "--version"], capture_output=True, text=True, check=True
    )
    logger.info("pip: %s", result.stdout.strip())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--compiler", required=True, help="expected compiler prefix, e.g. 'GCC 16.2.0'"
    )
    parser.add_argument(
        "--os-version", required=True, help="expected os-release VERSION_ID"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger.info("python: %s", sys.version.replace("\n", " "))
    check_compiler(args.compiler)
    check_free_threading()
    check_os(args.os_version)
    check_extension_modules()
    check_tls_trust_store()
    check_pip()
    logger.info("smoke test passed")


if __name__ == "__main__":
    main()
