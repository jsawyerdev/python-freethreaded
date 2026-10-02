# python-freethreaded

Free-threaded (`--disable-gil`) CPython container images, published to
`ghcr.io/jsawyerdev/python` for `linux/amd64` and `linux/arm64`, in two flavours:

- **Debian:** the official [docker-library/python](https://github.com/docker-library/python)
  Debian images with `--disable-gil`.
- **Ubuntu + GCC:** CPython compiled with the newest GCC release (from the official `gcc`
  image) and run on Ubuntu. See [Ubuntu + GCC image](#ubuntu--gcc-image).

```sh
docker run --rm -it ghcr.io/jsawyerdev/python:3.14t
docker run --rm -it ghcr.io/jsawyerdev/python:3.14t-ubuntu26.04
```

## When to use it

Free-threading lets several threads run Python code at the same time. It helps CPU-bound
work spread across threads, and costs elsewhere: single-threaded code runs slower and
memory use is higher. Small I/O-bound web services usually get slower, not faster.

Any compiled extension that does not declare free-threading support turns the GIL back on
for the whole process when it is imported; Python prints a `RuntimeWarning` saying so.
Check that your dependencies ship `cp314t` wheels.

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

### Schedule

`.github/workflows/build.yml`:

- daily: builds only when upstream has a new `PYTHON_VERSION` not yet published here;
- weekly (Monday): rebuilds unconditionally to pick up Debian security updates;
- manually via "Run workflow", and on every push to `main`.

To move to a new minor version, change `PY_MINOR` in the workflow.

## Ubuntu + GCC image

Built from `Dockerfile` by `.github/workflows/build-ubuntu.yml`.

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
- **Users:** `ubuntu:26.04` ships a user `ubuntu` with uid/gid 1000. Dockerfiles that run
  `useradd --uid 1000` must remove it first (`userdel --remove ubuntu`).

The build fails unless `smoke_test.py` passes inside the image: the interpreter was
compiled by the expected GCC, the GIL is disabled, the OS is the expected Ubuntu release,
every compiled stdlib extension imports, the TLS trust store is populated, and `pip`
runs.

### What was built

Each image records its build in `/usr/local/share/python-build/build-info.txt`: CPython
version and source checksum, compiler and linker versions, base images, configure flags,
`CFLAGS`/`LDFLAGS`, and the Ubuntu runtime packages. The workflow also writes it to each
run's job summary.

```sh
docker run --rm ghcr.io/jsawyerdev/python:3.14t-ubuntu26.04 \
  cat /usr/local/share/python-build/build-info.txt
```

### Tags

| Tag | Meaning |
| --- | --- |
| `3.14.8t-ubuntu26.04-gcc16.2.0` | the exact CPython, Ubuntu and GCC versions it was built from |
| `3.14t-ubuntu26.04` | the latest build for that minor version and Ubuntu release |

`*-amd64` / `*-arm64` tags are per-architecture intermediates.

### Schedule and updating

Rebuilt weekly (Monday) for Ubuntu security updates, manually, and when `Dockerfile`,
`smoke_test.py` or the workflow changes on `main`.

Versions are the `ARG` defaults at the top of `Dockerfile`; tags are derived from them. To
move to a newer GCC, Ubuntu or CPython, change `GCC_IMAGE`, `UBUNTU_IMAGE`, or
`PYTHON_VERSION` together with `PYTHON_SHA256` (from python.org or docker-library's
Dockerfile).

`.gitlab-ci.yml` builds the same `Dockerfile` (amd64 only) with Kaniko for a private
registry; it is not needed to use the published images.
