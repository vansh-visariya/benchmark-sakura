FROM python:3.13-slim

WORKDIR /tmp

COPY driver.py /tmp/driver.py

# No shell utilities beyond what Python needs; network is disabled at runtime.
CMD ["sleep", "infinity"]
