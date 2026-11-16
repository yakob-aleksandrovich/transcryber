# Base image: Wolfi (Chainguard). glibc-based, so the Python ML wheels used here
# (ctranslate2, PyAV, onnxruntime, cryptography) install exactly as on Debian,
# while the base has a much smaller package/CVE surface than debian:slim.
# Runs as the built-in nonroot user; see docker-compose.yml for the volume setup.
#
# Pinned by digest for reproducibility (Chainguard's free tier publishes only
# :latest / :latest-dev, so there is no version tag to pin). Refresh with:
#   docker buildx imagetools inspect cgr.dev/chainguard/wolfi-base:latest
# then update the sha256 below (and `docker pull` it so the new digest is local).
FROM cgr.dev/chainguard/wolfi-base:latest@sha256:833c48f1faf32c90e6f9501a2410a9aa28ceb2c594102edd4470053c30efa089

# python-3.12 / py3.12-pip: the interpreter + pip.
# libstdc++, libgomp: REQUIRED at runtime by ctranslate2 / onnxruntime (OpenMP).
# No ffmpeg package: faster-whisper decodes via PyAV, whose wheel bundles its own
# ffmpeg libraries (av.libs). The ffmpeg CLI is never called, so installing it
# would only add ~30 MB and extra CVE surface. (If an exotic container format
# ever fails, add `ffmpeg` back here.)
RUN apk add --no-cache \
      python-3.12 \
      py3.12-pip \
      libstdc++ \
      libgomp

WORKDIR /app

# Infra paths only — all app config (whisper, db, secret, token, users) lives in
# config.yaml, mounted at runtime. HF_HOME is where the model cache is stored.
ENV HF_HOME=/models \
    DATA_DIR=/app/data

COPY requirements.txt .
# --break-system-packages: this is a single-purpose container, so installing
# into the system interpreter (PEP 668 "externally managed") is fine here.
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

COPY app ./app

# Writable dirs owned by the built-in nonroot user (uid/gid 65532). When mounted
# as NAMED volumes, Docker initializes them with this ownership, so the app can
# write with no host-side chown and no root at runtime. See docker-compose.yml.
RUN mkdir -p /app/data /models && chown -R nonroot:nonroot /app/data /models

USER nonroot

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
