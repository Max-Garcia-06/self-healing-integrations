#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

cat <<'BANNER'
================================================================
  ShipFast just shipped v3. Three things changed:
    1. price_cents  ->  nested amount { value, currency }
    2. service_code ->  service_level
    3. new REQUIRED request header: X-Shipper-Id
  None of these facts appear in our prompt.
================================================================
BANNER
read -rp "Press enter to swap the vendor spec and regenerate... "

cp context/specs/shipfast/v3.json context/specs/shipfast/openapi.snapshot.json

echo
echo "---- INTENT (adapter prompt) ----"
git diff --stat prompts/shipfast_adapter_python.prompt | grep -q . \
  && git diff --stat prompts/shipfast_adapter_python.prompt \
  || echo "  0 files changed  <-- the intent did not change"
echo
echo "---- VENDOR WIRE FORMAT (pinned snapshot) ----"
git diff --stat context/specs/shipfast/openapi.snapshot.json
echo
echo "Regenerating from unchanged intent + changed wire format..."
echo "\$ pdd --force sync shipfast_adapter --budget 2.00 --skip-tests"
echo

# Clear the sync fingerprint so regeneration always runs. The prompt is
# unchanged; only the pinned snapshot moved. This is the moral equivalent of
# --force and does not weaken the regeneration.
mkdir -p .pdd/_parked
mv .pdd/meta/shipfast_adapter_python.json .pdd/_parked/ 2>/dev/null || true

START=$(date +%s)
pdd --force sync shipfast_adapter --budget 2.00 --skip-tests
END=$(date +%s)

echo
echo "---- GENERATED ADAPTER ----"
git diff --stat src/shipfast_adapter.py
echo
echo "Healed in $((END-START))s."
