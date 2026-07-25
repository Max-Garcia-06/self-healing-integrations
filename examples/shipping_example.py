"""Example usage of the shipping domain types module.

This script demonstrates how to construct the vendor-neutral domain
objects (Parcel, Address, Quote) defined in shipping.py, and how to
handle the module's exception types (NoServiceAvailable, ProviderTimeout)
that a carrier-integration layer would raise when calling into a
rate-lookup function built on top of these types.

Run this script directly:
    python examples/shipping_example.py
"""

import os
import sys

# Make the sibling "src" directory importable without assuming an
# installed package. This resolves relative to this file's location,
# so it works regardless of the current working directory.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from shipping import (
    Address,
    NoServiceAvailable,
    Parcel,
    ProviderTimeout,
    Quote,
)


def build_parcel() -> Parcel:
    """Construct a Parcel describing the physical package to be shipped.

    Returns:
        Parcel: A frozen, validated model with:
            - weight_grams (int): package weight in grams, must be > 0.
            - length_mm (int): package length in millimeters, must be > 0.
            - width_mm (int): package width in millimeters, must be > 0.
            - height_mm (int): package height in millimeters, must be > 0.
    """
    return Parcel(
        weight_grams=2500,
        length_mm=300,
        width_mm=200,
        height_mm=150,
    )


def build_address() -> Address:
    """Construct an Address describing the shipping destination.

    Returns:
        Address: A frozen, validated model with:
            - country_code (str): ISO 3166-1 alpha-2 code (auto-uppercased).
            - postal_code (str): destination postal/zip code, non-blank.
            - city (str): destination city name, non-blank.
            - state_or_province (str | None): optional region/state name.
    """
    return Address(
        country_code="us",  # will be normalized to "US"
        postal_code="94103",
        city="San Francisco",
        state_or_province="CA",
    )


def fake_rate_lookup(parcel: Parcel, destination: Address) -> Quote:
    """Simulate a carrier-agnostic rate lookup.

    In a real integration, this function would delegate to a specific
    carrier adapter, translate the Parcel/Address into that carrier's
    wire format, call it over HTTP, and translate the response back
    into a Quote. Here we just return a fixed Quote for demonstration.

    Args:
        parcel (Parcel): physical package attributes.
        destination (Address): shipping destination attributes.

    Returns:
        Quote: the resulting price, expressed as integer minor units
        (e.g. cents) plus an ISO 4217 currency code.

    Raises:
        NoServiceAvailable: if no carrier can service this shipment.
        ProviderTimeout: if the lookup exceeds an allotted time budget.
    """
    if destination.country_code not in {"US", "CA"}:
        raise NoServiceAvailable(
            f"No carrier available for country {destination.country_code!r}"
        )

    if parcel.weight_grams > 50_000:
        raise ProviderTimeout("Simulated timeout for oversized parcel lookup")

    # 1999 minor units == $19.99 USD.
    return Quote(amount_minor_units=1999, currency="usd")


def main() -> None:
    parcel = build_parcel()
    destination = build_address()

    print(f"Parcel: {parcel}")
    print(f"Destination: {destination}")

    try:
        quote = fake_rate_lookup(parcel, destination)
    except NoServiceAvailable as exc:
        print(f"No service available: {exc}")
        return
    except ProviderTimeout as exc:
        print(f"Provider timed out: {exc}")
        return

    # Quote.currency is normalized to uppercase by the validator.
    print(
        f"Quote received: {quote.amount_minor_units} "
        f"{quote.currency} minor units"
    )

    # Demonstrate that Quote is immutable (frozen=True).
    try:
        quote.amount_minor_units = 0  # type: ignore[misc]
    except Exception as exc:  # pydantic raises a validation-style error
        print(f"Quote is immutable as expected: {exc.__class__.__name__}")


if __name__ == "__main__":
    main()