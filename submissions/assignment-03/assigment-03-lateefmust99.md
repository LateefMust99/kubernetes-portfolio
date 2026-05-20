# Assignment 03 — Lateef Mustapha

# 1. Size comparison table

| Variant | Size | Layers | Stop time | Exit code |
|---|---|---|---|---|
| `cohort-greet:naive` | 1.63GB | 19 | ~5.3 s | 137 |
| `cohort-greet:multi` | 264MB | 21 | ~0.4 s | 0 |


---

# 2. Final image digest

```text
sha256:2fe8581b231458bd4689dbe76b7f6190d4dc8cebf393614d318d9ff51392e852" for cohort-greet:multi
```

---

# 3. Answers to the 7 questions

## Q1 — naive size + stop behaviour + why

The naive image size was approximately `1.63GB MB`. The container stop time was around `5 seconds`, and the exit code was `137`.

The exit code was `137` because the Dockerfile used the shell form of `CMD`:

```dockerfile
CMD gunicorn -b 0.0.0.0:8080 app:app
```

In shell form, Docker launches the application through `/bin/sh -c`, meaning the shell process becomes PID 1 instead of the Gunicorn process directly. When Docker sends a SIGTERM during `docker stop`, the shell does not properly forward the signal to Gunicorn, causing Docker to eventually force kill the container with SIGKILL after the timeout expires. SIGKILL results in exit code 137.

---

## Q2 — build output, CACHED vs rebuilt

Build output after modifying only `app.py`:

```text
CACHED [build 3/5] COPY requirements.txt .
CACHED [build 4/5] RUN pip install --no-cache-dir -r requirements.txt
[build 5/5] COPY app.py .
```

The `requirements.txt` layer and the `pip install` layer were cached because those files did not change. Only the `COPY app.py` layer rebuilt because Docker invalidates cache only for layers affected by changed files.

This demonstrates proper Docker layer ordering. By copying `requirements.txt` before `app.py`, dependency installation remains cached during application code changes, which significantly improves rebuild speed.

---

## Q3 — new stop time/exit + which change

The new stop time was approximately `0.4 seconds`, and the new exit code was `0`.

The improvement came from changing the Dockerfile from shell-form `CMD` to exec-form `CMD`:

```dockerfile
CMD ["gunicorn", "-b", "0.0.0.0:8080", "app:app"]
```

With exec-form syntax, Gunicorn becomes PID 1 directly inside the container. Docker sends SIGTERM directly to Gunicorn, allowing the application to shut down gracefully. Since the application also implemented a SIGTERM handler, the container exits cleanly before the timeout is reached.

---

## Q4 — size reduction breakdown

The multi-stage image was significantly smaller than the naive image, shrinking by approximately `84%`.

Several Dockerfile optimizations contributed to the reduction:

- Multi-stage builds removed unnecessary build dependencies from the final runtime image.
- Using `python:3.11-slim` reduced the overall base image footprint.
- The runtime image only copied the virtual environment from the build stage instead of carrying the full build toolchain.
- `.dockerignore` prevented unnecessary files such as `.git`, markdown files, and cache files from entering the image context.
- `--no-cache-dir` prevented pip from storing package caches inside image layers.

The largest savings came from eliminating unnecessary tooling and reducing duplicated layers.

---

## Q5 — cache-mount timings + CI relevance

Cold build timing:

```text
XX seconds
```

Warm cache-mount timing:

```text
XX seconds
```

The second build was faster because BuildKit cache mounts preserved pip package downloads even though the Docker layer cache was disabled using `--no-cache`.

This is especially useful in CI/CD systems where ephemeral runners often lose layer cache between builds. Persisting dependency caches remotely allows package installations to remain fast even when the Docker build cache itself is cold.

---

## Q6 — secret marker + what ARG would leak

Secret marker output:

```text
ee91
```

Leak check output:

```text
no leak
```

Using BuildKit secret mounts prevents sensitive values from being stored inside image layers or Docker build history.

If `ARG PYPI_TOKEN` had been used instead, the token could have leaked into:

- `docker image history`
- image metadata
- build cache
- CI/CD logs

Secret mounts inject the value temporarily only during the specific build step and do not persist it in the final image.

---

## Q7 — tag vs digest for k8s manifest

For production Kubernetes manifests, I would prefer using an image digest:

```yaml
image: cohort-greet@sha256:...
```

Using a digest guarantees exact image immutability and reproducibility because the digest uniquely identifies the image contents. Tags such as `latest` or semantic versions can be moved or overwritten later.

If the security team mandates strict reproducibility and supply chain verification, digest pinning becomes extremely important because it guarantees the cluster always deploys the exact validated image.

A semantic version combined with a Git SHA is useful for readability and traceability, but the digest provides the strongest guarantee of integrity.

---

# 4. Files

## Final `Dockerfile`

```dockerfile
# syntax=docker/dockerfile:1.7

FROM python:3.11.10-slim AS build

RUN python -m venv /opt/venv

ENV PATH=/opt/venv/bin:$PATH

WORKDIR /app

COPY requirements.txt .

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.txt

FROM python:3.11.10-slim AS runtime

COPY --from=build /opt/venv /opt/venv

ENV PATH=/opt/venv/bin:$PATH

WORKDIR /app

RUN useradd --create-home --uid 1000 app && \
    chown -R app:app /app

COPY app.py .

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/healthz')"

USER app

CMD ["gunicorn", "-b", "0.0.0.0:8080", "app:app"]
```

---

## `Dockerfile.naive`

```dockerfile
FROM python:3.11

WORKDIR /app

COPY . .

RUN pip install -r requirements.txt

EXPOSE 8080

CMD gunicorn -b 0.0.0.0:8080 app:app
```

---

## `Dockerfile.secret`

```dockerfile
FROM python:3.11-slim

RUN --mount=type=secret,id=pypi_token \
    TOKEN=$(cat /run/secrets/pypi_token) && \
    echo "$TOKEN" | cut -c1-4 > /where-token-was-used
```

---

## `.dockerignore`

```text
.git
.gitignore
__pycache__
*.pyc
Dockerfile*
*.md
.env*
```

---

# 5. Evidence

## docker image ls cohort-greet

```text
REPOSITORY     TAG             IMAGE ID       CREATED        SIZE
cohort-greet   secret          006b3e112f39   17 hours ago   212MB
cohort-greet   0.1.0           2fe8581b2314   17 hours ago   264MB
cohort-greet   0.1.0-4296484   2fe8581b2314   17 hours ago   264MB
cohort-greet   git-4296484     2fe8581b2314   17 hours ago   264MB
cohort-greet   multi           2fe8581b2314   17 hours ago   264MB
cohort-greet   naive           da97a3dd933e   25 hours ago   1.63GB
```

---

## docker image history cohort-greet:multi

```text
2fe8581b2314   17 hours ago    CMD ["gunicorn" "-b" "0.0.0.0:8080" "app:app…   0B        buildkit.dockerfile.v0
<missing>      17 hours ago    USER app                                        0B        buildkit.dockerfile.v0
<missing>      17 hours ago    HEALTHCHECK &{["CMD-SHELL" "python -c \"impo…   0B        buildkit.dockerfile.v0
<missing>      17 hours ago    EXPOSE map[8080/tcp:{}]                         0B        buildkit.dockerfile.v0
<missing>      17 hours ago    RUN /bin/sh -c chown -R app:app /app # build…   12.3kB    buildkit.dockerfile.v0
<missing>      17 hours ago    COPY app.py . # buildkit                        12.3kB    buildkit.dockerfile.v0
<missing>      17 hours ago    RUN /bin/sh -c useradd --create-home --uid 1…   69.6kB    buildkit.dockerfile.v0
<missing>      17 hours ago    WORKDIR /app                                    8.19kB    buildkit.dockerfile.v0
<missing>      17 hours ago    ENV PATH=/opt/venv/bin:/usr/local/bin:/usr/l…   0B        buildkit.dockerfile.v0
<missing>      17 hours ago    COPY /opt/venv /opt/venv # buildkit             34.4MB    buildkit.dockerfile.v0
<missing>      19 months ago   CMD ["python3"]                                 0B        buildkit.dockerfile.v0
<missing>      19 months ago   RUN /bin/sh -c set -eux;  for src in idle3 p…   16.4kB    buildkit.dockerfile.v0
<missing>      19 months ago   RUN /bin/sh -c set -eux;   savedAptMark="$(a…   55MB      buildkit.dockerfile.v0
<missing>      19 months ago   ENV PYTHON_SHA256=07a4356e912900e61a15cb0949…   0B        buildkit.dockerfile.v0
<missing>      19 months ago   ENV PYTHON_VERSION=3.11.10                      0B        buildkit.dockerfile.v0
<missing>      19 months ago   ENV GPG_KEY=A035C8C19219BA821ECEA86B64E628F8…   0B        buildkit.dockerfile.v0
<missing>      19 months ago   RUN /bin/sh -c set -eux;  apt-get update;  a…   9.53MB    buildkit.dockerfile.v0
<missing>      19 months ago   ENV LANG=C.UTF-8                                0B        buildkit.dockerfile.v0
<missing>      19 months ago   ENV PATH=/usr/local/bin:/usr/local/sbin:/usr…   0B        buildkit.dockerfile.v0
<missing>      19 months ago   # debian.sh --arch 'arm64' out/ 'bookworm' '…   108MB     debuerreotype 0.15
```

---

## secret marker output

```text
ee91
```

---

## leak check

```text
no leak
```

---

## hadolint output

```text
<empty output>
```

---

## build timing outputs

```text
Q5 — cache-mount timings + CI relevance:

Cold build:
10.762 total

Warm cache-mount build:
8.321 total

The second build saved approximately 2.4 seconds because the BuildKit cache mount preserved downloaded pip packages between builds even though the Docker layer cache was disabled using `--no-cache`.

This matters in CI/CD environments because ephemeral runners often start with an empty Docker layer cache. Using persistent cache mounts allows dependency downloads to be reused across pipeline runs, significantly improving build performance and reducing pipeline execution time.
```

---

# 6. One trade-off I had to make

I chose to use `python:3.11-slim` instead of Alpine Linux. Alpine images are smaller, but they often introduce compatibility issues with Python packages due to musl libc differences. Using the slim Debian-based image provided better compatibility and easier debugging while still keeping the image relatively lightweight.

---

# 7. One thing I'm still unsure about

I still want to better understand when registry-based remote BuildKit cache strategies become more efficient than traditional Docker layer caching in large-scale CI environments.
