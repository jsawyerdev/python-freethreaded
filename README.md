# python-freethreaded

Free-threaded (`--disable-gil`) CPython container images, built two ways:

- **Debian (GitHub Actions, GHCR):** the official
  [docker-library/python](https://github.com/docker-library/python) Debian images, for
  `linux/amd64` and `linux/arm64`.
- **Ubuntu + latest GCC (homelab GitLab, local registry):** CPython compiled with the
  official `gcc` image's toolchain and run on Ubuntu, `linux/amd64` only. See
  [Ubuntu + GCC image](#ubuntu--gcc-image).

## Debian images

The changes from upstream are `--disable-gil` in the `./configure` call and an
`apt-get upgrade` layer so pending Debian updates are applied before CPython is built.
Each build fails unless the resulting interpreter reports `Py_GIL_DISABLED == 1` and runs
with the GIL off.

### Tags

| Tag | Image |
| --- | --- |
| `3.14t`, `3.14t-trixie`, `3.14.Nt-trixie` | full Debian trixie (includes gcc for building C extensions) |
| `3.14t-slim-trixie`, `3.14.Nt-slim-trixie` | slim Debian trixie |

`*-amd64` / `*-arm64` tags are per-architecture intermediates; use the tags above.

```sh
docker pull ghcr.io/OWNER/python:3.14t
docker run --rm -it ghcr.io/OWNER/python:3.14t
```

### Schedule

`.github/workflows/build.yml`:

- daily: builds only when upstream has a new `PYTHON_VERSION` not yet published here;
- weekly (Monday): rebuilds unconditionally to pick up Debian security updates;
- manually via "Run workflow", and on every push to `main`.

To move to a new minor version, change `PY_MINOR` in the workflow.

## Ubuntu + GCC image

`Dockerfile`, built by `.gitlab-ci.yml` on the homelab GitLab runners (Kaniko) and pushed
to `192.168.1.202:5000/python-freethreaded`.

- **Compiler:** GCC from the official `gcc` image (`GCC_IMAGE`), copied into an Ubuntu
  build stage. CPython is compiled on Ubuntu, not inside the `gcc` image, because that
  image is Debian-based: its OpenSSL, SQLite and readline headers would not match the
  Ubuntu libraries the interpreter runs against.
- **Runtime:** `UBUNTU_IMAGE` with `apt-get upgrade` applied, plus only the shared
  libraries the interpreter links against (found with `ldd` at build time). No compiler
  is installed, so packages without a prebuilt `cp314t` wheel will not install.
- **Build:** the same `./configure` flags as docker-library/python plus `--disable-gil`
  (PGO, LTO, shared libpython), with Ubuntu's `dpkg-buildflags` hardening flags. Ubuntu's
  default `-flto=auto` is removed so CPython's own `--with-lto` controls LTO.

The build fails unless `smoke_test.py` passes inside the image: the interpreter was
compiled by the expected GCC, the GIL is disabled, the OS is the expected Ubuntu release,
every compiled stdlib extension imports, the TLS trust store is populated, and `pip`
runs.

### What was built

Each image records its build in `/usr/local/share/python-build/build-info.txt`: CPython
version and source checksum, compiler and linker versions, base images, configure flags,
`CFLAGS`/`LDFLAGS`, and the Ubuntu runtime packages. The `test-image` CI job prints it
with the image digest and keeps it as the `build-info.txt` artifact.

```sh
docker run --rm 192.168.1.202:5000/python-freethreaded:3.14.8t-ubuntu26.04-gcc16.2.0 \
  cat /usr/local/share/python-build/build-info.txt
```

The registry is plain HTTP: add `192.168.1.202:5000` to Docker's `insecure-registries`
before pulling.

### Tags

| Tag | Meaning |
| --- | --- |
| `<python>t-ubuntu<release>-gcc<gcc>`, e.g. `3.14.8t-ubuntu26.04-gcc16.2.0` | the versions it was built from |
| `<short commit sha>` | the commit that built it |

### Updating

Versions are the `ARG` defaults at the top of `Dockerfile`; the CI tag is derived from
them. To move to a newer GCC, Ubuntu or CPython, change `GCC_IMAGE`, `UBUNTU_IMAGE`, or
`PYTHON_VERSION` together with `PYTHON_SHA256` (from python.org or docker-library's
Dockerfile), and push to the default branch.
