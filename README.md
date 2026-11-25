# python-freethreaded

Free-threaded (`--disable-gil`) CPython container images, published to
`ghcr.io/jsawyerdev/python` for `linux/amd64` and `linux/arm64`, in two flavours:

- **Debian:** the official [docker-library/python](https://github.com/docker-library/python)
  Debian images with `--disable-gil`.
- **Ubuntu + GCC:** the newest CPython 3.15 and 3.14 patch releases compiled with the
  newest GCC release (from the official `gcc` image) and run on Ubuntu. See
  [Ubuntu + GCC image](#ubuntu--gcc-image).

```sh
docker run --rm -it ghcr.io/jsawyerdev/python:3.14t
docker run --rm -it ghcr.io/jsawyerdev/python:3.15t-ubuntu26.04
```

## When to use it

Free-threading lets several threads run Python code at the same time. It helps CPU-bound
work spread across threads, and costs elsewhere: single-threaded code runs slower and
memory use is higher. Small I/O-bound web services usually get slower, not faster.

Any compiled extension that does not declare free-threading support turns the GIL back on
for the whole process when it is imported; Python prints a `RuntimeWarning` saying so.
Check that your dependencies ship free-threaded wheels for your Python version (`cp314t`,
`cp315t`, or `abi3t` on 3.15+).

## Benchmark

`bench/run.sh` runs `bench/bench.py` (standard library only) in three CPython 3.14.8
images: the official GIL build, the Debian free-threaded build (GCC 14) and the Ubuntu
free-threaded build (GCC 16). It does three rounds, rotating the order, and prints medians
relative to the GIL build: six single-thread micro-benchmarks, thread scaling at 1, 2, 4
and 8 threads for a fixed amount of CPU-bound work, and peak RSS of fresh interpreters for
a few allocation patterns.

```sh
bench/run.sh
```

Micro-benchmarks exaggerate the single-thread cost of free-threading compared with real
applications; run the same comparison on your own workload before deciding.

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

To move to a new minor version, change `PY_MINOR` in the workflow once docker-library has a
folder for it (release candidates live in `3.N-rc`). Debian images are currently built for
3.14 only.

## Ubuntu + GCC image

Built from `Dockerfile` by `.github/workflows/build-ubuntu.yml`.

- **Compiler:** GCC from the official `gcc` image (`GCC_IMAGE`), copied into an Ubuntu
  build stage. CPython is compiled on Ubuntu, not inside the `gcc` image, because that
  image is Debian-based: its OpenSSL, SQLite and readline headers would not match the
  Ubuntu libraries the interpreter runs against.
- **Runtime:** `UBUNTU_IMAGE` with `apt-get upgrade` applied, plus only the shared
  libraries the interpreter links against (found with `ldd` at build time). No compiler
  is installed, so packages without a prebuilt free-threaded wheel will not install.
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
docker run --rm ghcr.io/jsawyerdev/python:3.15t-ubuntu26.04 \
  cat /usr/local/share/python-build/build-info.txt
```

### Tags

| Tag | Meaning |
| --- | --- |
| `3.15.2t-ubuntu26.04-gcc16.2.0`, `3.14.10t-ubuntu26.04-gcc16.2.0` | the exact CPython, Ubuntu and GCC versions it was built from |
| `3.15t-ubuntu26.04`, `3.14t-ubuntu26.04` | the newest CPython patch of that minor, built with the newest GCC; moves on every release |

`*-amd64` / `*-arm64` tags are per-architecture intermediates.

### Versions

Nothing is pinned by hand except Ubuntu. Every CI run starts with `resolve_versions.py`,
which picks:

- **GCC:** the highest `X.Y.Z` tag of the official `gcc` image, from the
  [official-images manifest](https://github.com/docker-library/official-images/blob/master/library/gcc);
- **CPython:** the newest stable patch release of each minor in `PYTHON_MINORS`
  (currently 3.15 and 3.14), with its source tarball's SHA256 from python.org's release API.
  The Dockerfile verifies the download against that checksum.

```sh
python3 resolve_versions.py               # JSON, used by GitHub Actions
python3 resolve_versions.py --format env  # KEY=value, used by GitLab CI
```

To publish a new minor version or stop publishing one, edit `PYTHON_MINORS` in
`resolve_versions.py` and the matching `PY_MINOR` matrix in `.gitlab-ci.yml`. To move to a
newer Ubuntu release, change `UBUNTU_IMAGE` in `Dockerfile`.

`Dockerfile` has no default for `GCC_IMAGE`, `PYTHON_VERSION` or `PYTHON_SHA256`; pass them
when building by hand:

```sh
eval "$(python3 resolve_versions.py --format env)"
docker build --build-arg GCC_IMAGE="gcc:$GCC_VERSION" \
  --build-arg PYTHON_VERSION="$PYTHON_3_15_VERSION" \
  --build-arg PYTHON_SHA256="$PYTHON_3_15_SHA256" .
```

### Schedule

`.github/workflows/build-ubuntu.yml`:

- daily: builds each minor whose exact tag (CPython patch + GCC version) is not yet
  published, so a new GCC or CPython release ships within a day;
- weekly (Monday): rebuilds everything to pick up Ubuntu security updates;
- manually via "Run workflow", and when `Dockerfile`, `smoke_test.py`,
  `resolve_versions.py` or the workflow changes on `main`.

`.gitlab-ci.yml` builds the same `Dockerfile` (amd64 only, both minors) with Kaniko for a
private registry; it is not needed to use the published images. It resolves versions the
same way and runs on a GitLab pipeline schedule, manually, or when those files change. Each
scheduled run rebuilds both minors. It pushes the exact tag, the `3.Nt-ubuntu26.04` minor
tag, `latest` (newest minor) and a `<commit>-py3.N` tag used by its test job.
