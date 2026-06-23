#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "=== letsgamble paper trading ==="
echo "Make sure IBKR Gateway is running and authenticated."
echo ""

python -m src.main "$@"
