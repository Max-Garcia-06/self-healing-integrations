#!/usr/bin/env bash
#
# scripts/pdd_regen.sh — regenerate the ShipFast config + adapter modules
# via PDD, working around quirks found while wiring this up:
#
#   1. `pdd generate` on a prompt whose output file already exists takes an
#      incremental-patch path. On this repo's prompt diffs that path hits an
#      internal PDD schema-validation bug and produces invalid Python.
#      Clearing the target file first forces full generation instead, which
#      does not hit the bug.
#   2. The generated adapter has occasionally imported from a module name
#      the model invented instead of this repo's real package paths
#      (src.types.shipping / src.config.shipfast). `pdd crash` fixes this
#      reliably given a real traceback, so after generating we try the
#      import and, if it fails, feed the traceback to `pdd crash`.
#   3. `pdd crash` itself is occasionally flaky and can overwrite the file
#      with garbage (observed once: the entire file replaced by the single
#      token `true`) instead of a real fix. We syntax-check its output and
#      retry from the last known-good generated version rather than
#      compounding a corrupt file across attempts.
#
# Called by scripts/demo.sh as PDD_REGEN_CMD. Exits non-zero on any failure
# so the caller's `die` fires.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
# Python adds a *file* argument's own directory to sys.path[0], not cwd, so
# running the repro script (which mktemp puts under /tmp) would misresolve
# the `integrations`/`src` packages regardless of the adapter's actual
# import statements. Force resolution against the repo root instead.
export PYTHONPATH="$PWD"

ADAPTER="integrations/shipfast/adapter.py"
ADAPTER_PROMPT="integrations/shipfast/adapter_python.prompt"
MAX_CRASH_ATTEMPTS=3

echo "-- regenerating src/config/shipfast.py --"
: > src/config/shipfast.py
uv run pdd --force generate src/config/shipfast_python.prompt \
  --output src/config/shipfast.py

echo "-- regenerating $ADAPTER --"
: > "$ADAPTER"
uv run pdd --force generate "$ADAPTER_PROMPT" --output "$ADAPTER"

GENERATED_BACKUP="$(mktemp -t adapter_generated.XXXXXX.py)"
REPRO_FILE="$(mktemp -t adapter_import_repro.XXXXXX.py)"
ERR_FILE="$(mktemp -t adapter_import_check.XXXXXX.txt)"
trap 'rm -f "$GENERATED_BACKUP" "$REPRO_FILE" "$ERR_FILE"' EXIT
cp "$ADAPTER" "$GENERATED_BACKUP"
echo "from integrations.shipfast.adapter import get_quote" > "$REPRO_FILE"

adapter_ok() {
  uv run python -m py_compile "$ADAPTER" 2>/dev/null \
    && uv run python "$REPRO_FILE" > "$ERR_FILE" 2>&1
}

if ! adapter_ok; then
  attempt=1
  while [ "$attempt" -le "$MAX_CRASH_ATTEMPTS" ]; do
    echo "-- generated adapter is broken (attempt $attempt/$MAX_CRASH_ATTEMPTS), fixing via pdd crash --"
    cat "$ERR_FILE"
    uv run pdd --force crash "$ADAPTER_PROMPT" "$ADAPTER" "$REPRO_FILE" "$ERR_FILE" \
      --output "$ADAPTER" --output-program "$REPRO_FILE" || true

    if adapter_ok; then
      echo "-- fix succeeded --"
      break
    fi

    echo "-- pdd crash did not produce working code, restoring last known-good generation and retrying --"
    cp "$GENERATED_BACKUP" "$ADAPTER"
    attempt=$((attempt + 1))
  done
fi

echo "-- verifying adapter imports cleanly --"
uv run python -c "from integrations.shipfast.adapter import get_quote"
echo "-- regeneration complete --"
