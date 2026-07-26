#!/usr/bin/env bash
#
# scripts/demo.sh — one-command self-healing integrations demo.
#
# Tells the whole story end to end:
#   v2 mock -> generated v2 adapter passes -> switch provider to v3 ->
#   stale adapter fails -> regenerate adapter -> regenerated adapter passes ->
#   evidence: prompt intent unchanged, spec changed, adapter changed, rule preserved.
#
# Guarantees:
#   * starts and stops its own mock (never touches a foreign one on the port)
#   * always restores the mock to v2 and kills the mock on exit (even on Ctrl-C)
#   * exits 0 ONLY when the full story succeeds
#   * exits 3 if the regeneration command is not yet wired (friendly stop)
#   * exits 1 on any unexpected failure
#
# The regeneration command is intentionally NOT guessed. When PDD is configured,
# set PDD_REGEN_CMD below (or export it) and steps 5-7 run automatically.

set -u -o pipefail

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${SHIPFAST_PORT:-8081}"
BASE="http://127.0.0.1:${PORT}"

# The documented PDD regeneration command. LEAVE EMPTY until PDD is configured
# in the repo (.pddrc / .pdd). When empty, the demo stops cleanly at STEP 5.
# Example once wired:  PDD_REGEN_CMD='pdd sync integrations/shipfast/adapter.prompt'
PDD_REGEN_CMD="${PDD_REGEN_CMD:-}"

# Non-secret demo credentials for the mock. NOT real secrets.
export SHIPFAST_BASE_URL="$BASE"
export SHIPFAST_API_KEY="demo-key"
export SHIPFAST_ACCOUNT_NUMBER="DEMO-ACCT-0001"
export SHIPFAST_SHIPPER_ID="shipper-123"

MOCK_PID=""
MOCK_LOG="$(mktemp -t shipfast-mock.XXXXXX.log)"
SNAP_DIR="$(mktemp -d -t shipfast-demo.XXXXXX)"

# --------------------------------------------------------------------------- #
# Presentation helpers
# --------------------------------------------------------------------------- #
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  BOLD=$'\033[1m'; DIM=$'\033[2m'; GREEN=$'\033[32m'; RED=$'\033[31m'
  YELLOW=$'\033[33m'; CYAN=$'\033[36m'; RESET=$'\033[0m'
else
  BOLD=""; DIM=""; GREEN=""; RED=""; YELLOW=""; CYAN=""; RESET=""
fi

rule() { printf '%s\n' "================================================"; }
banner() {
  echo; rule
  printf '%s%s%s\n' "$BOLD" "SELF-HEALING INTEGRATIONS" "$RESET"
  printf '%s\n' "========================="
}
step()  { echo; printf '%s%s%s\n' "$BOLD$CYAN" "STEP $1" "$RESET"; printf '%s\n' "$2"; echo; }
ok()    { printf '%s✓ %s%s\n' "$GREEN" "$1" "$RESET"; }
warn()  { printf '%s%s%s\n' "$YELLOW" "$1" "$RESET"; }
bad()   { printf '%s✗ %s%s\n' "$RED" "$1" "$RESET"; }
plain() { printf '%s\n' "$1"; }

nap() { python3 -c 'import time,sys; time.sleep(float(sys.argv[1]))' "$1" 2>/dev/null || true; }

# --------------------------------------------------------------------------- #
# Cleanup — always runs. Restores v2 and stops the mock WE started.
# --------------------------------------------------------------------------- #
cleanup() {
  if [ -n "$MOCK_PID" ]; then
    curl -s -X POST "$BASE/admin/version" \
      -H 'Content-Type: application/json' -d '{"version":"v2"}' >/dev/null 2>&1 || true
    kill "$MOCK_PID" >/dev/null 2>&1 || true
    wait "$MOCK_PID" 2>/dev/null || true
  fi
  rm -f "$MOCK_LOG" 2>/dev/null || true
  rm -rf "$SNAP_DIR" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

die() { echo; bad "$1"; echo; exit "${2:-1}"; }

# --------------------------------------------------------------------------- #
# Mock + provider helpers
# --------------------------------------------------------------------------- #
active_version() {
  curl -s "$BASE/health" 2>/dev/null \
    | python3 -c 'import sys,json; print(json.load(sys.stdin)["activeVersion"])' 2>/dev/null
}

switch_version() {
  curl -s -X POST "$BASE/admin/version" \
    -H 'Content-Type: application/json' -d "{\"version\":\"$1\"}" >/dev/null 2>&1
  [ "$(active_version)" = "$1" ]
}

start_mock() {
  if curl -s -o /dev/null "$BASE/health" 2>/dev/null; then
    die "Port $PORT is already serving something. Stop it and re-run (never demo against an unknown server)."
  fi
  ( cd "$REPO" && exec uv run uvicorn mock.server:app --host 127.0.0.1 --port "$PORT" ) \
    >"$MOCK_LOG" 2>&1 &
  MOCK_PID=$!
  for _ in $(seq 1 80); do
    if curl -s -o /dev/null "$BASE/health" 2>/dev/null; then return 0; fi
    if ! kill -0 "$MOCK_PID" 2>/dev/null; then
      echo; bad "Mock failed to start. Log:"; sed 's/^/    /' "$MOCK_LOG"; return 1
    fi
    nap 0.2
  done
  return 1
}

# Runs the generated adapter once. Sets globals: RA_KIND, RA_A, RA_B.
run_adapter() {
  local line
  line="$(cd "$REPO" && uv run python scripts/run_adapter.py 2>/dev/null)"
  RA_KIND="${line%%::*}"
  local rest="${line#*::}"
  RA_A="${rest%%::*}"
  RA_B="${rest##*::}"
}

# --------------------------------------------------------------------------- #
# The demo
# --------------------------------------------------------------------------- #
banner

# ---- STEP 1: start mock on v2 --------------------------------------------- #
step 1 "Starting ShipFast mock (v2)..."
start_mock || die "Could not start the ShipFast mock."
[ "$(active_version)" = "v2" ] || die "Mock did not come up on v2."
ok "running"

# ---- STEP 2: generated v2 adapter succeeds -------------------------------- #
step 2 "Running generated v2 adapter..."
run_adapter
if [ "$RA_KIND" = "ADAPTER_OK" ] && [ "$RA_A" = "1240" ] && [ "$RA_B" = "USD" ]; then
  ok "PASS"; plain "Ground Standard"; plain "$RA_A $RA_B"
  V2_AMOUNT="$RA_A"; V2_CURRENCY="$RA_B"
else
  die "Expected the v2 adapter to return 1240 USD, got: $RA_KIND $RA_A $RA_B"
fi

# ---- STEP 3: switch provider to v3 ---------------------------------------- #
step 3 "Switching provider to v3..."
switch_version v3 || die "Failed to switch the provider to v3."
ok "provider updated"

# ---- STEP 4: stale adapter fails ------------------------------------------ #
step 4 "Running stale adapter..."
run_adapter
if [ "$RA_KIND" = "ADAPTER_OK" ]; then
  die "Stale v2 adapter unexpectedly SUCCEEDED against v3 — the break was not demonstrated."
fi
ok "EXPECTED FAILURE"
echo
plain "Reason:"
case "$RA_B" in
  *410*) plain "410 Gone"; plain "Vendor contract changed" ;;
  *)     plain "${RA_A}: ${RA_B}" ;;
esac

# Snapshot the current (stale, v2) adapter + prompt so STEP 7 can prove what
# regeneration did and did not change.
cp "$REPO/integrations/shipfast/adapter.py"     "$SNAP_DIR/adapter.before"    2>/dev/null || true
cp "$REPO/integrations/shipfast/adapter.prompt" "$SNAP_DIR/prompt.before"     2>/dev/null || true

# ---- STEP 5: regenerate ---------------------------------------------------- #
step 5 "Regenerating adapter..."
if [ -z "$PDD_REGEN_CMD" ]; then
  warn "The PDD regeneration command is not wired yet."
  plain "${DIM}(no .pddrc / .pdd in this repo; set PDD_REGEN_CMD at the top of scripts/demo.sh)${RESET}"
  echo
  printf '%s%s%s\n' "$YELLOW" "TODO: insert regeneration command here" "$RESET"
  echo
  plain "${DIM}Steps 1-4 succeeded. Steps 5-7 will run automatically once the command is set.${RESET}"
  echo; rule
  exit 3
fi
plain "${DIM}\$ ${PDD_REGEN_CMD}${RESET}"
if ! ( cd "$REPO" && eval "$PDD_REGEN_CMD" ); then
  die "Regeneration command failed: $PDD_REGEN_CMD"
fi
ok "regenerated"

# ---- STEP 6: regenerated adapter succeeds against v3 ---------------------- #
step 6 "Running regenerated adapter..."
run_adapter
if [ "$RA_KIND" = "ADAPTER_OK" ] && [ "$RA_A" = "1240" ] && [ "$RA_B" = "USD" ]; then
  ok "PASS"; echo; plain "Ground Standard"; plain "$RA_A $RA_B"
  V6_AMOUNT="$RA_A"; V6_CURRENCY="$RA_B"
else
  die "Regenerated adapter did not return 1240 USD against v3, got: $RA_KIND $RA_A $RA_B"
fi

# ---- STEP 7: evidence ------------------------------------------------------ #
step 7 "Evidence"

# Prompt INTENT: compare with the vendor-spec pin lines stripped, so swapping
# which snapshot is pinned does not count as an intent change.
intent() { grep -v -E '<include|openapi\.snapshot\.json|v3\.json' "$1" 2>/dev/null; }
if diff <(intent "$SNAP_DIR/prompt.before") <(intent "$REPO/integrations/shipfast/adapter.prompt") >/dev/null 2>&1; then
  prompt_ok=1; else prompt_ok=0; fi

# Adapter: must have changed.
if cmp -s "$SNAP_DIR/adapter.before" "$REPO/integrations/shipfast/adapter.py"; then
  adapter_changed=0; else adapter_changed=1; fi

# Vendor spec: the two committed contracts differ by construction.
if cmp -s "$REPO/context/specs/shipfast/openapi.snapshot.json" "$REPO/context/specs/shipfast/v3.json"; then
  spec_changed=0; else spec_changed=1; fi

# Business rule preserved: same result before and after the heal.
if [ "${V2_AMOUNT:-}" = "${V6_AMOUNT:-}" ] && [ "${V2_CURRENCY:-}" = "${V6_CURRENCY:-}" ]; then
  business_ok=1; else business_ok=0; fi

echo; plain "Prompt intent:"
[ "$prompt_ok" = 1 ]      && ok "unchanged"  || { bad "changed"; EVID_FAIL=1; }
echo; plain "Vendor specification:"
[ "$spec_changed" = 1 ]   && ok "changed"    || { bad "unchanged"; EVID_FAIL=1; }
echo; plain "Generated adapter:"
[ "$adapter_changed" = 1 ] && ok "changed"   || { bad "unchanged"; EVID_FAIL=1; }
echo; plain "Business rule:"
[ "$business_ok" = 1 ]    && ok "preserved"  || { bad "broken"; EVID_FAIL=1; }

if [ "${EVID_FAIL:-0}" = 1 ]; then
  die "Evidence check failed — the self-heal claim is not fully supported."
fi

echo; rule
printf '%s%s%s\n' "$BOLD$GREEN" "SELF-HEAL COMPLETE" "$RESET"
printf '%s\n' "=================="
echo
exit 0
