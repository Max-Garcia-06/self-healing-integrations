"""ShipFast shipping-rate adapter.

Translates Northwind's internal Parcel/Address types into a ShipFast rate
request, calls the ShipFast rates endpoint, and translates the response back
into our internal Quote type.
"""
from __future__ import annotations

import time

import httpx
from pydantic import BaseModel

from src.types.shipping import Address, NoServiceAvailable, Parcel, ProviderTimeout, Quote
from src.config.shipfast import ShipFastSettings

_TIMEOUT_SECONDS = 3.0
_RETRY_DELAY_SECONDS = 0.2
_RATES_PATH = "/v2/rates"
_GROUND_MODES = {"surface", "ground"}


class _WireParcel(BaseModel):
    weight_oz: int
    length_in: float
    width_in: float
    height_in: float


class _WireAddress(BaseModel):
    line1: str | None = None
    line2: str | None = None
    city: str | None = None
    region: str | None = None
    postal_code: str
    country_code: str


class _RateRequest(BaseModel):
    account_number: str
    parcel: _WireParcel
    destination: _WireAddress


class _Rate(BaseModel):
    service_code: str
    service_name: str
    transit_mode: str
    price_cents: int
    currency: str


class _RateResponse(BaseModel):
    request_id: str | None = None
    rates: list[_Rate] = []


def _grams_to_oz(grams: int) -> int:
    return round(grams * 0.03527396195)


def _mm_to_in(mm: int) -> float:
    return mm * 0.0393700787


def _build_request(parcel: Parcel, destination: Address, settings: ShipFastSettings) -> _RateRequest:
    return _RateRequest(
        account_number=settings.account_number.get_secret_value(),
        parcel=_WireParcel(
            weight_oz=_grams_to_oz(parcel.weight_grams),
            length_in=_mm_to_in(parcel.length_mm),
            width_in=_mm_to_in(parcel.width_mm),
            height_in=_mm_to_in(parcel.height_mm),
        ),
        destination=_WireAddress(
            line1=destination.line1,
            line2=destination.line2,
            city=destination.city,
            region=destination.state_or_province,
            postal_code=destination.postal_code,
            country_code=destination.country_code,
        ),
    )


def get_quote(parcel: Parcel, destination: Address) -> Quote:
    settings = ShipFastSettings()
    request = _build_request(parcel, destination, settings)
    url = f"{settings.base_url}{_RATES_PATH}"
    headers = settings.vendor_headers()
    timeout = httpx.Timeout(_TIMEOUT_SECONDS)

    payload = request.model_dump(mode="json")

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, json=payload, headers=headers)
            if response.status_code == 429:
                time.sleep(_RETRY_DELAY_SECONDS)
                response = client.post(url, json=payload, headers=headers)
    except httpx.TimeoutException as exc:
        raise ProviderTimeout("ShipFast rate request timed out") from exc

    if response.status_code != 200:
        raise httpx.HTTPStatusError(
            f"ShipFast rate request failed with status {response.status_code}",
            request=response.request,
            response=response,
        )

    parsed = _RateResponse.model_validate(response.json())

    eligible = [rate for rate in parsed.rates if rate.transit_mode in _GROUND_MODES]
    if not eligible:
        raise NoServiceAvailable("No eligible ground services available")

    cheapest = min(eligible, key=lambda r: (r.price_cents, r.service_code))

    return Quote(amount_minor_units=cheapest.price_cents, currency=cheapest.currency)