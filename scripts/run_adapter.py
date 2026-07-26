"""Demo helper: run the generated ShipFast adapter once and report the result.

This is glue for scripts/demo.sh — it does NOT reimplement any adapter logic.
It calls the real, teammate-owned `get_quote(parcel, destination)` interface
and prints a single machine-parseable line so the shell harness can react:

  ADAPTER_OK::<amount_minor_units>::<currency>     (exit 0)  business success
  ADAPTER_ERROR::<ExceptionName>::<message>        (exit 20) expected business failure
                                                             (e.g. vendor 410 after a v3 switch)
  ADAPTER_FATAL::<ExceptionName>::<message>        (exit 21) unexpected failure
                                                             (missing env, import error, bug)

Requires the ShipFast connection env vars to be set by the caller
(SHIPFAST_BASE_URL / SHIPFAST_API_KEY / SHIPFAST_ACCOUNT_NUMBER /
SHIPFAST_SHIPPER_ID). demo.sh sets non-secret demo values.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the repo root importable regardless of the caller's cwd, so the
# adapter's absolute imports (`src.*`, `integrations.*`) resolve.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    try:
        from integrations.shipfast.adapter import get_quote
        from src.types.shipping import Address, NoServiceAvailable, Parcel, ProviderTimeout
    except Exception as exc:  # import-time failure = environment/codegen problem
        print(f"ADAPTER_FATAL::{type(exc).__name__}::{exc}")
        return 21

    # Fixed demo shipment: a 3 lb parcel to Denver, CO 80202 (see
    # user_stories/story__cheapest_ground_rate.md). The mock returns a fixed
    # rate table regardless of the exact parcel, so this is deterministic.
    try:
        parcel = Parcel(weight_grams=1361, length_mm=300, width_mm=200, height_mm=150)
        destination = Address(
            country_code="US", postal_code="80202", city="Denver", state_or_province="CO"
        )
    except Exception as exc:
        print(f"ADAPTER_FATAL::{type(exc).__name__}::{exc}")
        return 21

    try:
        quote = get_quote(parcel, destination)
    except (NoServiceAvailable, ProviderTimeout) as exc:
        # Expected, well-typed business failure — this is what a stale adapter
        # raises when the vendor contract has moved out from under it.
        print(f"ADAPTER_ERROR::{type(exc).__name__}::{exc}")
        return 20
    except Exception as exc:  # anything else is unexpected
        print(f"ADAPTER_FATAL::{type(exc).__name__}::{exc}")
        return 21

    print(f"ADAPTER_OK::{quote.amount_minor_units}::{quote.currency}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
