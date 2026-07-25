#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
git checkout -- context/specs/shipfast/openapi.snapshot.json src/shipfast_adapter.py
echo "Reset to v2. Ready to rehearse again."
