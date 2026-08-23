FROM python:3.13-slim

# Dedicated unprivileged user: model code runs as nobody, so even a sandbox
# escape cannot read the driver's environment or write outside tmpfs.
RUN groupadd -r sakura && useradd -r -g sakura -u 10001 \
      --home-dir /tmp --shell /usr/sbin/nologin sakura

WORKDIR /tmp

RUN mkdir -p /opt/sakura && \
    chown -R sakura:sakura /tmp
COPY --chown=root:sakura driver.py /opt/sakura/driver.py

USER sakura

# No shell utilities beyond what Python needs; network is disabled at runtime.
CMD ["sleep", "infinity"]
