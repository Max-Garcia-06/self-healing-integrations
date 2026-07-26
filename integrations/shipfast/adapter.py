"""ShipFast shipping-rate adapter.

Translates Northwind's internal Parcel/Address into a ShipFast rate
request, calls the ShipFast rates endpoint, and translates the response
into an internal Quote. Chooses the cheapest eligible ground service.
"""
from __future__ import annotations

import time

import httpx
from pydantic import BaseModel, ConfigDict

from src.types.shipping import Address, NoServiceAvailable, Parcel, ProviderTimeout, Quote
from src.config.shipfast import ShipFastSettings

_GROUND_MODES = frozenset({"surface", "ground"})
_RETRY_DELAY_SECONDS = 0.2
_TIMEOUT_SECONDS = 3.0


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
    parcel: _WireParcel
    destination: _WireAddress


class _WireMoney(BaseModel):
    model_config = ConfigDict(frozen=True)
    value: int
    currency: str


class _WireRate(BaseModel):
    model_config = ConfigDict(frozen=True)
    service_level: str
    service_name: str
    transit_mode: str
    amount: _WireMoney


class _WireRateResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    request_id: str | None = None
    rates: list[_WireRate] = []


def _grams_to_oz(grams: int) -> int:
    return round(grams / 28.349523125)


def _mm_to_in(mm: int) -> float:
    return mm / 25.4


def _build_request(parcel: Parcel, destination: Address) -> _WireRateRequest:
    return _WireRateRequest(
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
    ground_rates = [r for r in response.rates if r.transit_mode in _GROUND_MODES]
    if not ground_rates:
        raise NoServiceAvailable()
    return min(ground_rates, key=lambda r: (r.amount.value, r.service_level))


def get_quote(parcel: Parcel, destination: Address) -> Quote:
    """Get the cheapest ground-service shipping quote from ShipFast."""
    settings = ShipFastSettings()
    request_body = _build_request(parcel, destination)
    url = f"{settings.base_url}/v3/rates"
    headers = settings.vendor_headers()
    timeout = httpx.Timeout(_TIMEOUT_SECONDS)

    try:
        response = _do_request(url, headers, request_body, timeout)
        if response.status_code == 429:
            time.sleep(_RETRY_DELAY_SECONDS)
            response = _do_request(url, headers, request_body, timeout)
    except httpx.TimeoutException as exc:
        raise ProviderTimeout() from exc

    if response.status_code != 200:
        raise NoServiceAvailable()

    parsed = _WireRateResponse.model_validate(response.json())
    cheapest = _select_cheapest_ground(parsed)

    return Quote(
        amount_minor_units=cheapest.amount.value,
        currency=cheapest.amount.currency,
    )


def _do_request(
    url: str,
    headers: dict[str, str],
    request_body: _WireRateRequest,
    timeout: httpx.Timeout,
) -> httpx.Response:
    with httpx.Client(timeout=timeout) as client:
        return client.post(
            url,
            headers=headers,
            json=request_body.model_dump(),
        )