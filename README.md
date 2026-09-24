# python-freethreaded

Free-threaded (`--disable-gil`) builds of the official
[docker-library/python](https://github.com/docker-library/python) Debian images, for
`linux/amd64` and `linux/arm64`.

The only change from upstream is `--disable-gil` in the `./configure` call. Each build
fails unless the resulting interpreter reports `Py_GIL_DISABLED == 1` and runs with the
GIL off.

## Tags

| Tag | Image |
| --- | --- |
| `3.14t`, `3.14t-trixie`, `3.14.Nt-trixie` | full Debian trixie (includes gcc for building C extensions) |
| `3.14t-slim-trixie`, `3.14.Nt-slim-trixie` | slim Debian trixie |

`*-amd64` / `*-arm64` tags are per-architecture intermediates; use the tags above.

```sh
docker pull ghcr.io/OWNER/python:3.14t
docker run --rm -it ghcr.io/OWNER/python:3.14t
```

## Schedule

`.github/workflows/build.yml`:

- daily: builds only when upstream has a new `PYTHON_VERSION` not yet published here;
- weekly (Monday): rebuilds unconditionally to pick up Debian security updates;
- manually via "Run workflow", and on every push to `main`.

To move to a new minor version, change `PY_MINOR` in the workflow.
