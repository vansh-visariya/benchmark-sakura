#!/usr/bin/env bash
set -euo pipefail

IMAGE="${SAKURA_EXECUTOR_IMAGE:-sakura-executor:0.1.0}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

docker build -t "$IMAGE" "$SCRIPT_DIR"
echo "Built $IMAGE"
