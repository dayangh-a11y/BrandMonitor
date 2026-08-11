#!/usr/bin/env bash
# Start the Prediction API for Render / cloud hosts.
# Uses host 0.0.0.0 and $PORT (Render injects PORT).
set -euo pipefail

PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"

exec uvicorn src.api.main:app --host "${HOST}" --port "${PORT}"
