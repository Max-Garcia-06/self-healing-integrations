"""
Example usage of the ShipFast shipping-rate adapter.

This script demonstrates how to request a shipping quote from ShipFast
by constructing internal `Parcel` and `Address` domain objects and calling
`get_quote`, which handles translation to/from ShipFast's wire format,
HTTP communication, retries, and error handling.

Configuration (base URL, API key, account number) is read from environment
variables via `ShipFastSettings` (a pydantic-settings `BaseSettings`
subclass), so no secrets are passed directly in code. Set these env vars
before running, e.g.:

    export SHIPFAST_BASE_URL="https://api.shipfast.example.com"
    export SHIPFAST_API_KEY="sk_live_..."
    export SHIPFAST_ACCOUNT_NUMBER="ACC12345"

Run this script directly:

    python examples/shipfast_adapter_example.py
"""
from __future__ import annotations

import os
import sys

# Ensure the `src` directory is importable when running this example
# directly from the `examples/` folder, without requiring installation.
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "src")
)

from shipfast_adapter import get_quote
from shipping.domain import Address, NoServiceAvailable, Parcel, ProviderTimeout


def main() -> None:
    # Parcel: physical attributes of the package to be shipped.
    #   weight_grams (int): total weight in grams.
    #   length_mm, width_mm, height_mm (int): dimensions in millimeters.
    parcel = Parcel(
        weight_grams=2200,
        length_mm=300,
        width_mm=200,
        height_mm=150,
    )

    # Address: destination attributes needed to request a rate.
    #   country_code (str): ISO 3166-1 alpha-2 country code.
    #   postal_code (str): destination postal/ZIP code.
    #   city (str): destination city name.
    #   state_or_province (str | None): optional state/province code.
    destination = Address(
        country_code="US",
        postal_code="94107",
        city="San Francisco",
        state_or_province="CA",
    )

    try:
        # get_quote(parcel, destination) -> Quote
        #   Calls ShipFast's rates endpoint and returns the cheapest
        #   available ground service quote.
        #
        # Returns:
        #   Quote with:
        #     amount_minor_units (int): price in integer minor units
        #       (e.g., cents), inclusive of carrier surcharges.
        #     currency (str): ISO 4217 currency code (e.g., "USD").
        quote = get_quote(parcel, destination)
        print(
            f"Cheapest ground quote: {quote.amount_minor_units} "
            f"{quote.currency} (minor units)"
        )
    except NoServiceAvailable as exc:
        # Raised when no eligible ground service is returned, or when
        # ShipFast rate-limits the request twice, or on other non-2xx
        # responses.
        print(f"No shipping service available: {exc}")
    except ProviderTimeout as exc:
        # Raised when the ShipFast request doesn't complete within
        # the configured timeout (3 seconds per attempt).
        print(f"ShipFast request timed out: {exc}")


if __name__ == "__main__":
    main()