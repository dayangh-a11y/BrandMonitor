#!/usr/bin/env bash
# Periodic Persian live OpenAI QA for private beta.
# Requires OPENAI_API_KEY. Writes under output/ai_eval_live_fa/.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=.
OUT_DIR="${OUT_DIR:-output/ai_eval_live_fa}"
LIMIT="${LIMIT:-50}"
python3 scripts/evaluate_ai.py \
  --live \
  --require-live \
  --language fa \
  --limit "$LIMIT" \
  --out-dir "$OUT_DIR"
echo "Live FA QA written to $OUT_DIR"
