#!/usr/bin/env bash
# The whole heal, end to end. Assumes the mock is running on :8099.
#   .venv/bin/python -m uvicorn mock.server:app --port 8099 &
set -uo pipefail
cd "$(dirname "$0")/.."

source scripts/pdd-env.sh
export SHIPFAST_BASE_URL=http://localhost:8099
export SHIPFAST_API_KEY=sk_test_shipfast_demo
export SHIPFAST_ACCOUNT_NUMBER=ACCT-99812
export SHIPFAST_SHIPPER_ID=SHIP-4471

PY=.venv/bin/python
vendor () { curl -s -X POST localhost:8099/admin/version \
    -H 'content-type: application/json' -d "{\"version\":\"$1\"}" >/dev/null; }

echo "=============================================================="
echo " 1. BASELINE — vendor on v2, adapter generated from v2 spec"
echo "=============================================================="
BASE=v2-baseline   # git tag pinning the verified v2 stack
git checkout -q "$BASE" -- context/specs/shipfast/openapi.snapshot.json \
    src/config/shipfast.py integrations/shipfast/adapter.py
vendor v2
$PY scripts/quote_demo.py

echo
echo "=============================================================="
echo " 2. THE BREAK — ShipFast ships v3. Three things changed:"
echo "      price_cents  -> nested amount { value, currency }"
echo "      service_code -> service_level"
echo "      new REQUIRED request header: X-Shipper-Id"
echo "    None of these facts appear anywhere in our prompt."
echo "=============================================================="
vendor v3
$PY scripts/quote_demo.py

echo
echo "=============================================================="
echo " 3. THE HEAL — replace ONLY the pinned vendor spec, rerun PDD"
echo "=============================================================="
cp context/specs/shipfast/v3.json context/specs/shipfast/openapi.snapshot.json
echo "changed files:"; git status --porcelain -- context src integrations

START=$(date +%s)
pdd --local --force --output-cost costs.csv \
    generate src/config/shipfast_python.prompt --output src/config/shipfast.py \
    2>&1 | grep -E "✓ Step|^Error"
pdd --local --force --output-cost costs.csv \
    generate integrations/shipfast/adapter_python.prompt \
    --output integrations/shipfast/adapter.py 2>&1 | grep -E "✓ Step|^Error"
END=$(date +%s)
echo "healed in $((END-START))s"

echo
echo "=============================================================="
echo " 4. THE THREE-COLUMN DIFF"
echo "=============================================================="
echo "-- durable intent (prompts) --"
git diff --stat "$BASE" -- '*.prompt' | grep -q . \
  && git diff --stat "$BASE" -- '*.prompt' \
  || echo "   0 files changed   <<< THE INTENT DID NOT CHANGE"
echo "-- vendor wire format (pinned snapshot) --"
git diff --stat "$BASE" -- context/specs/shipfast/openapi.snapshot.json
echo "-- generated code --"
git diff --stat "$BASE" -- src/config/shipfast.py integrations/shipfast/adapter.py

echo
echo "=============================================================="
echo " 5. PROOF — same vendor, stale code vs regenerated code"
echo "=============================================================="
for V in v2 v3; do
  vendor "$V"
  echo "vendor serving $V:"
  printf "   stale v2 stack : "; $PY scripts/stale_demo.py
  printf "   regenerated    : "; $PY scripts/quote_demo.py
done
vendor v3
