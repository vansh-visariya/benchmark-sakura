FROM python:3.13-slim

# Dedicated unprivileged user: model code runs as nobody, so even a sandbox
# escape cannot read the driver's environment or write outside tmpfs.
RUN groupadd -r sakura && useradd -r -g sakura -u 10001 \
      --home-dir /tmp --shell /usr/sbin/nologin sakura

WORKDIR /workspace

# Shell utilities terminal-agent tasks exercise (git, text tools, process
# inspection) plus pytest for test-driven tasks.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git grep sed gawk findutils procps coreutils && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir pytest && \
    mkdir -p /opt/sakura /opt/tests /workspace && \
    chown -R sakura:sakura /tmp /workspace

COPY --chown=root:sakura driver.py /opt/sakura/driver.py

USER sakura

# Network is disabled at runtime; rootfs is read-only except the tmpfs mounts.
CMD ["sleep", "infinity"]
