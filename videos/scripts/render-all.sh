#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v vhs >/dev/null || { echo "VHS not found: brew install vhs"; exit 1; }
mkdir -p recordings
for tape in tapes/*.tape; do
  echo "Rendering $tape"
  vhs "$tape"
done
echo "Done. Videos are in recordings/"
