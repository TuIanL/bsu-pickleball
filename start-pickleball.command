#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# start-local-runtime generates one per-run API token and passes it to API, worker, and Vite.
"$SCRIPT_DIR/scripts/start-local-runtime.sh"

printf '\nPress Enter to close this window...'
read -r _
