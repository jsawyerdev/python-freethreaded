# Free-threaded CPython compiled with the official gcc image's toolchain and run on Ubuntu.
#
# The compiler is copied out of GCC_IMAGE into an Ubuntu build stage rather than compiling
# inside GCC_IMAGE itself: GCC_IMAGE is Debian-based, so building there would compile against
# Debian's OpenSSL/SQLite/readline headers and then run against Ubuntu's libraries.
# Building on UBUNTU_IMAGE keeps headers and runtime libraries from the same release.
# Kaniko builds this file in CI, so it avoids BuildKit-only syntax (heredocs, cache mounts).

ARG GCC_IMAGE=gcc:16.2.0
ARG UBUNTU_IMAGE=ubuntu:26.04
ARG PYTHON_VERSION=3.14.8
ARG PYTHON_SHA256=c2215904f02b175596dc49351585104f4bc20341e1c47378b26a2c274360ce73

FROM ${GCC_IMAGE} AS gcc

FROM ${UBUNTU_IMAGE} AS build

ARG GCC_IMAGE
ARG UBUNTU_IMAGE
ARG PYTHON_VERSION
ARG PYTHON_SHA256

# The toolchain only needs libc, libm and libzstd at run time. Its runtime libraries
# (libgcc_s, libatomic, ...) in /usr/local/lib64 are deliberately left off the loader path
# so the PGO training run links against Ubuntu's copies, exactly as the final image will.
COPY --from=gcc /usr/local/ /usr/local/

RUN set -eux; \
	export DEBIAN_FRONTEND=noninteractive; \
	apt-get update; \
	apt-get upgrade -y; \
	apt-get install -y --no-install-recommends \
		binutils \
		ca-certificates \
		dpkg-dev \
		libatomic1 \
		libbluetooth-dev \
		libbz2-dev \
		libc6-dev \
		libdb-dev \
		libffi-dev \
		libgdbm-dev \
		liblzma-dev \
		libncurses-dev \
		libreadline-dev \
		libsqlite3-dev \
		libssl-dev \
		libzstd-dev \
		libzstd1 \
		make \
		uuid-dev \
		wget \
		xz-utils \
		zlib1g-dev \
	; \
# CC stays plain "gcc" so sysconfig does not point C-extension builds at a path that
# only exists here; assert that it resolves to the copied toolchain.
	test "$(command -v gcc)" = /usr/local/bin/gcc; \
	test "$(gcc -dumpfullversion)" = "${GCC_IMAGE##*:}"

RUN set -eux; \
	wget -O python.tar.xz "https://www.python.org/ftp/python/${PYTHON_VERSION%%[a-z]*}/Python-$PYTHON_VERSION.tar.xz"; \
	echo "$PYTHON_SHA256 *python.tar.xz" | sha256sum -c -; \
	mkdir -p /usr/src/python; \
	tar --extract --directory /usr/src/python --strip-components=1 --file python.tar.xz; \
	rm python.tar.xz; \
	\
	cd /usr/src/python; \
	gnuArch="$(dpkg-architecture --query DEB_BUILD_GNU_TYPE)"; \
	./configure \
		CC=gcc \
		--build="$gnuArch" \
		--disable-gil \
		--enable-loadable-sqlite-extensions \
		--enable-optimizations \
		--enable-option-checking=fatal \
		--enable-shared \
		--with-lto \
		--with-ensurepip \
	; \
	nproc="$(nproc)"; \
# Ubuntu's dpkg-buildflags already add frame pointers and hardening, but also inject
# -flto=auto -ffat-lto-objects, which would fight CPython's own --with-lto.
	export DEB_BUILD_MAINT_OPTIONS=optimize=-lto; \
	EXTRA_CFLAGS="$(dpkg-buildflags --get CFLAGS)"; \
	LDFLAGS="$(dpkg-buildflags --get LDFLAGS) -Wl,--strip-all"; \
	make -j "$nproc" "EXTRA_CFLAGS=$EXTRA_CFLAGS" "LDFLAGS=$LDFLAGS"; \
# https://github.com/docker-library/python/issues/784
	rm python; \
	make -j "$nproc" "EXTRA_CFLAGS=$EXTRA_CFLAGS" "LDFLAGS=$LDFLAGS -Wl,-rpath='\$\$ORIGIN/../lib'" python; \
	make install DESTDIR=/out; \
	\
	info=/out/usr/local/share/python-build; \
	mkdir -p "$info"; \
	{ \
		echo "python:         $PYTHON_VERSION (free-threaded, --disable-gil)"; \
		echo "source:         https://www.python.org/ftp/python/${PYTHON_VERSION%%[a-z]*}/Python-$PYTHON_VERSION.tar.xz"; \
		echo "source sha256:  $PYTHON_SHA256"; \
		echo "compiler image: $GCC_IMAGE"; \
		echo "compiler:       $(gcc --version | head -n 1)"; \
		echo "linker:         $(ld --version | head -n 1)"; \
		echo "build image:    $UBUNTU_IMAGE (toolchain copied from $GCC_IMAGE)"; \
		echo "runtime image:  $UBUNTU_IMAGE"; \
		echo "configure:      $(sed -n "s/^CONFIG_ARGS=[[:space:]]*//p" Makefile)"; \
		echo "EXTRA_CFLAGS:   $EXTRA_CFLAGS"; \
		echo "LDFLAGS:        $LDFLAGS"; \
	} > "$info/build-info.txt"; \
	\
	cd /; \
	rm -rf /usr/src/python; \
	find /out/usr/local -depth \
		\( \
			\( -type d -a \( -name test -o -name tests -o -name idle_test \) \) \
			-o \( -type f -a \( -name '*.pyc' -o -name '*.pyo' -o -name 'libpython*.a' \) \) \
		\) -exec rm -rf '{}' + \
	; \
	\
# Resolve the shared libraries the install needs to the Ubuntu packages that ship them.
# Any unresolved library or symbol version fails the build here instead of at run time.
# libpython is found through ldconfig in the final image; point the loader at it here.
	find /out/usr/local -type f -executable -exec env LD_LIBRARY_PATH=/out/usr/local/lib ldd '{}' ';' > /tmp/ldd.txt 2>/dev/null || true; \
	if grep -E 'not found' /tmp/ldd.txt; then exit 1; fi; \
	awk '/=>/ { so = $(NF-1); if (index(so, "/out/") == 1) { next }; gsub("^/(usr/)?", "", so); printf "*%s\n", so }' /tmp/ldd.txt \
		| sort -u \
		| xargs -r dpkg-query --search \
		| awk 'sub(":$", "", $1) { print $1 }' \
		| sort -u \
		> "$info/runtime-packages.txt"; \
	rm /tmp/ldd.txt; \
	test -s "$info/runtime-packages.txt"; \
	echo "runtime pkgs:   $(tr '\n' ' ' < "$info/runtime-packages.txt")" >> "$info/build-info.txt"; \
	cat "$info/build-info.txt"

FROM ${UBUNTU_IMAGE}

ARG GCC_IMAGE
ARG UBUNTU_IMAGE
ARG PYTHON_VERSION
ARG VCS_REF=unknown
ARG BUILD_DATE

LABEL org.opencontainers.image.title="python-freethreaded" \
	org.opencontainers.image.description="CPython ${PYTHON_VERSION} free-threaded, compiled with ${GCC_IMAGE} on ${UBUNTU_IMAGE}" \
	org.opencontainers.image.version="${PYTHON_VERSION}" \
	org.opencontainers.image.revision="${VCS_REF}" \
	org.opencontainers.image.created="${BUILD_DATE}" \
	org.opencontainers.image.base.name="${UBUNTU_IMAGE}"

COPY --from=build /out/usr/local/ /usr/local/

RUN set -eux; \
	export DEBIAN_FRONTEND=noninteractive; \
	apt-get update; \
	apt-get upgrade -y; \
	xargs -a /usr/local/share/python-build/runtime-packages.txt \
		apt-get install -y --no-install-recommends ca-certificates netbase tzdata; \
	apt-get dist-clean; \
	ldconfig; \
	for src in pip3 pydoc3 python3 python3-config; do \
		dst="$(echo "$src" | tr -d 3)"; \
		[ -s "/usr/local/bin/$src" ]; \
		[ ! -e "/usr/local/bin/$dst" ]; \
		ln -svT "$src" "/usr/local/bin/$dst"; \
	done

COPY smoke_test.py /usr/local/share/python-build/smoke_test.py

RUN set -eux; \
	PYTHONDONTWRITEBYTECODE=1 python3 /usr/local/share/python-build/smoke_test.py \
		--compiler "GCC ${GCC_IMAGE##*:}" \
		--os-version "${UBUNTU_IMAGE##*:}"; \
	echo "vcs ref:        $VCS_REF" >> /usr/local/share/python-build/build-info.txt

CMD ["python3"]
