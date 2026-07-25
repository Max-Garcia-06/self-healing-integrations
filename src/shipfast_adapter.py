"""ShipFast shipping-rate adapter.

Translates Northwind's internal Parcel/Address into a ShipFast rate request,
calls the ShipFast rates endpoint, and translates the response into our
internal Quote type.
"""
from __future__ import annotations

import time

import httpx
from pydantic import BaseModel, ConfigDict

from src.shipping import Parcel, Address, Quote, NoServiceAvailable, ProviderTimeout
from src.shipfast_config import ShipFastSettings

_GRAMS_PER_OZ = 28.3495
_MM_PER_IN = 25.4

_GROUND_MODES = frozenset({"surface", "ground"})

_TIMEOUT_SECONDS = 3.0
_RETRY_DELAY_SECONDS = 0.2


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


def _to_wire_parcel(parcel: Parcel) -> _WireParcel:
    return _WireParcel(
        weight_oz=round(parcel.weight_grams / _GRAMS_PER_OZ),
        length_in=parcel.length_mm / _MM_PER_IN,
        width_in=parcel.width_mm / _MM_PER_IN,
        height_in=parcel.height_mm / _MM_PER_IN,
    )


def _to_wire_address(address: Address) -> _WireAddress:
    return _WireAddress(
        postal_code=address.postal_code,
        country_code=address.country_code,
        city=address.city,
        region=address.state_or_province,
    )


def get_quote(parcel: Parcel, destination: Address) -> Quote:
    settings = ShipFastSettings()

    request_body = _WireRateRequest(
        account_number=settings.account_number_value(),
        parcel=_to_wire_parcel(parcel),
        destination=_to_wire_address(destination),
    )

    url = f"{settings.base_url}/v3/rates"
    timeout = httpx.Timeout(_TIMEOUT_SECONDS)
    headers = settings.vendor_headers()

    response = _send_with_retry(url, headers, request_body, timeout)

    if response.status_code != 200:
        raise NoServiceAvailable(
            f"ShipFast rate request failed with status {response.status_code}"
        )

    parsed = _WireRateResponse.model_validate(response.json())

    ground_rates = [
        rate for rate in parsed.rates if rate.transit_mode in _GROUND_MODES
    ]
    if not ground_rates:
        raise NoServiceAvailable("No ground services available from ShipFast")

    cheapest = min(
        ground_rates, key=lambda rate: (rate.amount.value, rate.service_level)
    )

    return Quote(
        amount_minor_units=cheapest.amount.value,
        currency=cheapest.amount.currency,
    )


def _send_with_retry(
    url: str,
    headers: dict[str, str],
    request_body: _WireRateRequest,
    timeout: httpx.Timeout,
) -> httpx.Response:
    payload = request_body.model_dump()

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, headers=headers, json=payload)
    except httpx.TimeoutException as exc:
        raise ProviderTimeout("ShipFast rate request timed out") from exc

    if response.status_code == 429:
        time.sleep(_RETRY_DELAY_SECONDS)
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise ProviderTimeout("ShipFast rate request timed out") from exc

    return response