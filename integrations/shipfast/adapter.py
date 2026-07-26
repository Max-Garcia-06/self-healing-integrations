"""ShipFast shipping-rate adapter.

Translates Northwind's internal Parcel/Address types into ShipFast wire
requests, calls the ShipFast rates endpoint, and translates the response
into an internal Quote.
"""
from __future__ import annotations

import time

import httpx
from pydantic import BaseModel, ConfigDict

from src.types.shipping import Address, NoServiceAvailable, Parcel, ProviderTimeout, Quote
from src.config.shipfast import ShipFastSettings

_TIMEOUT_SECONDS = 3.0
_RETRY_DELAY_SECONDS = 0.2
_GROUND_MODES = {"surface", "ground"}

_OZ_PER_GRAM = 1 / 28.3495
_IN_PER_MM = 1 / 25.4


class _ShipFastParcel(BaseModel):
    model_config = ConfigDict(frozen=True)
    weight_oz: int
    length_in: float
    width_in: float
    height_in: float


class _ShipFastAddress(BaseModel):
    model_config = ConfigDict(frozen=True)
    postal_code: str
    country_code: str
    city: str | None = None
    region: str | None = None


class _ShipFastRateRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    account_number: str
    parcel: _ShipFastParcel
    destination: _ShipFastAddress


class _ShipFastRate(BaseModel):
    model_config = ConfigDict(frozen=True)
    service_code: str
    service_name: str
    transit_mode: str
    price_cents: int
    currency: str


class _ShipFastRateResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    request_id: str | None = None
    rates: list[_ShipFastRate] = []


def _to_shipfast_parcel(parcel: Parcel) -> _ShipFastParcel:
    return _ShipFastParcel(
        weight_oz=round(parcel.weight_grams * _OZ_PER_GRAM),
        length_in=parcel.length_mm * _IN_PER_MM,
        width_in=parcel.width_mm * _IN_PER_MM,
        height_in=parcel.height_mm * _IN_PER_MM,
    )


def _to_shipfast_address(address: Address) -> _ShipFastAddress:
    return _ShipFastAddress(
        postal_code=address.postal_code,
        country_code=address.country_code,
        city=address.city,
        region=address.state_or_province,
    )


def _post_rates(
    client: httpx.Client, settings: ShipFastSettings, body: _ShipFastRateRequest
) -> httpx.Response:
    return client.post(
        f"{settings.base_url}/v2/rates",
        json=body.model_dump(mode="json"),
        headers=settings.vendor_headers(),
        timeout=httpx.Timeout(_TIMEOUT_SECONDS),
    )


def get_quote(parcel: Parcel, destination: Address) -> Quote:
    """Fetch the cheapest available ground service quote from ShipFast."""
    settings = ShipFastSettings()

    request_body = _ShipFastRateRequest(
        account_number=settings.account_number.get_secret_value(),
        parcel=_to_shipfast_parcel(parcel),
        destination=_to_shipfast_address(destination),
    )

    try:
        with httpx.Client() as client:
            response = _post_rates(client, settings, request_body)
            if response.status_code == 429:
                time.sleep(_RETRY_DELAY_SECONDS)
                response = _post_rates(client, settings, request_body)
    except httpx.TimeoutException as exc:
        raise ProviderTimeout("ShipFast rate request timed out") from exc

    if response.status_code != 200:
        raise NoServiceAvailable(
            f"ShipFast rate request failed with status {response.status_code}"
        )

    parsed = _ShipFastRateResponse.model_validate(response.json())

    ground_rates = [r for r in parsed.rates if r.transit_mode in _GROUND_MODES]
    if not ground_rates:
        raise NoServiceAvailable("No ground services available from ShipFast")

    best = min(ground_rates, key=lambda r: (r.price_cents, r.service_code))

    return Quote(amount_minor_units=best.price_cents, currency=best.currency)
