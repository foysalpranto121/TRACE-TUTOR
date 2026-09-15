# Execution environment for student-submitted code.
#
# Build once, from the repository root:
#   docker build -f backend/tutor/sandbox.Dockerfile -t trace-tutor-runner:1 backend/tutor
#
# The container is started with --network none, --read-only, --cap-drop ALL and memory,
# CPU and PID caps (see sandbox.py), so nothing here needs to be hardened further; the
# image only has to provide the toolchains.
FROM debian:bookworm-slim

RUN apt-get update \
 && apt-get install --no-install-recommends -y \
      gcc g++ libc6-dev python3-minimal \
 && rm -rf /var/lib/apt/lists/*

# Student code runs as a non-root user with no home and no login shell. The workdir is
# bind-mounted at /work by the runner.
RUN useradd --uid 65532 --no-create-home --shell /usr/sbin/nologin runner
USER 65532:65532

WORKDIR /work
