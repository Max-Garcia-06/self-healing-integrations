"""ShipFast shipping-rate adapter."""
from __future__ import annotations

import time

import httpx
from pydantic import BaseModel, ConfigDict

from src.config.shipfast import ShipFastSettings
from src.types.shipping import Address, NoServiceAvailable, Parcel, ProviderTimeout, Quote

GROUND_TRANSIT_MODES = {"surface", "ground"}
_RETRY_DELAY_SECONDS = 0.2
_TIMEOUT_SECONDS = 3.0


class _VendorParcel(BaseModel):
    model_config = ConfigDict(frozen=True)
    weight_oz: int
    length_in: float
    width_in: float
    height_in: float


class _VendorAddress(BaseModel):
    model_config = ConfigDict(frozen=True)
    line1: str | None = None
    line2: str | None = None
    city: str | None = None
    region: str | None = None
    postal_code: str
    country_code: str


class _VendorRateRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    account_number: str
    parcel: _VendorParcel
    destination: _VendorAddress


class _VendorRate(BaseModel):
    model_config = ConfigDict(frozen=True)
    service_code: str
    service_name: str
    transit_mode: str
    price_cents: int
    currency: str
    estimated_days: int | None = None


class _VendorRateResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    request_id: str | None = None
    rates: list[_VendorRate] = []


def _grams_to_oz(grams: int) -> int:
    return round(grams / 28.349523125)


def _mm_to_in(mm: int) -> float:
    return mm / 25.4


def _build_request(parcel: Parcel, destination: Address, account_number: str) -> _VendorRateRequest:
    vendor_parcel = _VendorParcel(
        weight_oz=_grams_to_oz(parcel.weight_grams),
        length_in=_mm_to_in(parcel.length_mm),
        width_in=_mm_to_in(parcel.width_mm),
        height_in=_mm_to_in(parcel.height_mm),
    )
    vendor_address = _VendorAddress(
        line1=destination.line1,
        line2=destination.line2,
        city=destination.city,
        region=destination.state_or_province,
        postal_code=destination.postal_code,
        country_code=destination.country_code,
    )
    return _VendorRateRequest(
        account_number=account_number,
        parcel=vendor_parcel,
        destination=vendor_address,
    )


def _select_cheapest_ground(rates: list[_VendorRate]) -> _VendorRate:
    eligible = [r for r in rates if r.transit_mode in GROUND_TRANSIT_MODES]
    if not eligible:
        raise NoServiceAvailable("No eligible ground services available.")
    eligible.sort(key=lambda r: (r.price_cents, r.service_code))
    return eligible[0]


def get_quote(parcel: Parcel, destination: Address) -> Quote:
    settings = ShipFastSettings()

    request = _build_request(parcel, destination, settings.account_number.get_secret_value())
    headers = settings.vendor_headers()
    timeout = httpx.Timeout(_TIMEOUT_SECONDS)
    url = f"{settings.base_url}/v2/rates"

    body = request.model_dump()

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, json=body, headers=headers)
            if response.status_code == 429:
                time.sleep(_RETRY_DELAY_SECONDS)
                response = client.post(url, json=body, headers=headers)
    except httpx.TimeoutException as exc:
        raise ProviderTimeout("ShipFast rate request timed out.") from exc

    if response.status_code != 200:
        raise NoServiceAvailable(
            f"ShipFast rate request failed with status {response.status_code}."
        )

    parsed = _VendorRateResponse.model_validate(response.json())
    cheapest = _select_cheapest_ground(parsed.rates)

    return Quote(amount_minor_units=cheapest.price_cents, currency=cheapest.currency)