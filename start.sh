#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BRIDGE_DIR="$PROJECT_ROOT/mt5_bridge"

echo "==> Starting Docker Compose..."
cd "$PROJECT_ROOT"
docker compose up -d --build

echo "==> Waiting for Docker services..."
timeout_seconds=180
start_time=$SECONDS

while true; do
    if ! docker compose ps --all --format json | python -c '
import json, sys
data = sys.stdin.read().strip()
if not data:
    raise SystemExit(1)
services = [json.loads(line) for line in data.splitlines() if line.strip()]
bad = [
    s for s in services
    if s.get("State", "").lower() != "running"
    or (
        s.get("Health")
        and s["Health"].lower() not in ("healthy", "starting")
    )
]
raise SystemExit(1 if bad else 0)
'; then
        if (( SECONDS - start_time >= timeout_seconds )); then
            docker compose ps --all
            echo "ERROR: Docker services did not become ready in time." >&2
            exit 1
        fi
        sleep 3
        continue
    fi
    break
done

echo "==> Docker services are running."
echo "==> Entering MT5 bridge directory..."
cd "$BRIDGE_DIR"

if [[ ! -f ".venv/scripts/activate" ]]; then
    echo "ERROR: Bridge virtual environment not found at $BRIDGE_DIR/.venv" >&2
    echo "Create the environment and install bridge dependencies first." >&2
    exit 1
fi

# Activate the bridge virtual environment.
source .venv/scripts/activate

echo "==> Starting MT5 bridge on port 9000..."
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 9000