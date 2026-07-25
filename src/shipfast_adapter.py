"""ShipFast shipping-rate adapter.

Translates Northwind's internal Parcel/Address into a ShipFast rate request,
calls the ShipFast rates endpoint, and translates the response into our
internal Quote type.
"""
from __future__ import annotations

import time

import httpx
from pydantic import BaseModel, ConfigDict, field_validator

from shipping.domain import Address, NoServiceAvailable, Parcel, ProviderTimeout, Quote
from shipping.shipfast_settings import ShipFastSettings

_TIMEOUT_SECONDS = 3.0
_RETRY_DELAY_SECONDS = 0.2

_GROUND_MODES = {"surface", "ground"}


# --- Vendor wire DTOs (ShipFast-specific, defined only here) ---------------

class _WireParcel(BaseModel):
    model_config = ConfigDict(frozen=True)

    weight_oz: int
    length_in: float
    width_in: float
    height_in: float


class _WireAddress(BaseModel):
    model_config = ConfigDict(frozen=True)

    postal_code: str
    country_code: str
    city: str | None = None
    region: str | None = None


class _WireRateRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    account_number: str
    parcel: _WireParcel
    destination: _WireAddress


class _WireSurcharge(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str | None = None
    amount_cents: int | None = None


class _WireRate(BaseModel):
    model_config = ConfigDict(frozen=True)

    service_code: str
    service_name: str
    transit_mode: str
    price_cents: int
    currency: str
    estimated_days: int | None = None
    surcharges: list[_WireSurcharge] | None = None

    @field_validator("transit_mode")
    @classmethod
    def _validate_transit_mode(cls, v: str) -> str:
        return v


class _WireRateResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: str | None = None
    rates: list[_WireRate] = []


def _grams_to_oz(grams: int) -> int:
    return round(grams / 28.349523125)


def _mm_to_in(mm: int) -> float:
    return mm / 25.4


def _to_wire_request(parcel: Parcel, destination: Address, settings: ShipFastSettings) -> _WireRateRequest:
    return _WireRateRequest(
        account_number=settings.account_number_value(),
        parcel=_WireParcel(
            weight_oz=_grams_to_oz(parcel.weight_grams),
            length_in=_mm_to_in(parcel.length_mm),
            width_in=_mm_to_in(parcel.width_mm),
            height_in=_mm_to_in(parcel.height_mm),
        ),
        destination=_WireAddress(
            postal_code=destination.postal_code,
            country_code=destination.country_code,
            city=destination.city,
            region=destination.state_or_province,
        ),
    )


def _select_cheapest_ground(response: _WireRateResponse) -> _WireRate:
    ground = [r for r in response.rates if r.transit_mode in _GROUND_MODES]
    if not ground:
        raise NoServiceAvailable("No eligible ground services returned by ShipFast.")
    ground.sort(key=lambda r: (r.price_cents, r.service_code))
    return ground[0]


def get_quote(parcel: Parcel, destination: Address) -> Quote:
    """Get the cheapest available ground shipping quote from ShipFast."""
    settings = ShipFastSettings()
    wire_request = _to_wire_request(parcel, destination, settings)
    headers = settings.vendor_headers()
    timeout = httpx.Timeout(_TIMEOUT_SECONDS)

    url = f"{settings.base_url}/v2/rates"
    body = wire_request.model_dump()

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, json=body, headers=headers)

            if response.status_code == 429:
                time.sleep(_RETRY_DELAY_SECONDS)
                response = client.post(url, json=body, headers=headers)
    except httpx.TimeoutException as exc:
        raise ProviderTimeout("ShipFast rate request timed out.") from exc

    if response.status_code == 200:
        wire_response = _WireRateResponse.model_validate(response.json())
        cheapest = _select_cheapest_ground(wire_response)
        return Quote(amount_minor_units=cheapest.price_cents, currency=cheapest.currency)

    if response.status_code == 429:
        raise NoServiceAvailable("ShipFast rate limited request twice; no quote obtained.")

    raise NoServiceAvailable(
        f"ShipFast rate request failed with status {response.status_code}."
    )