"""ShipFast shipping-rate adapter.

Translates Northwind's internal Parcel and Address types into a ShipFast
rate request, calls the ShipFast rates endpoint, and translates the
response into our internal Quote type.
"""
from __future__ import annotations

import time

import httpx
from pydantic import BaseModel, ConfigDict

from src.types.shipping import (
    Address,
    NoServiceAvailable,
    Parcel,
    ProviderTimeout,
    Quote,
)
from src.config.shipfast import ShipFastSettings

_GROUND_MODES = {"surface", "ground"}
_TIMEOUT_SECONDS = 3.0
_RETRY_DELAY_SECONDS = 0.2


class _MoneyDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    value: int
    currency: str


class _RateDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    service_level: str
    service_name: str
    transit_mode: str
    amount: _MoneyDTO


class _RateResponseDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: str | None = None
    rates: list[_RateDTO] = []


class _ParcelDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    weight_oz: int
    length_in: float
    width_in: float
    height_in: float


class _AddressDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    city: str | None = None
    region: str | None = None
    postal_code: str
    country_code: str


class _RateRequestDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    account_number: str
    parcel: _ParcelDTO
    destination: _AddressDTO


def _to_parcel_dto(parcel: Parcel) -> _ParcelDTO:
    ounces = round(parcel.weight_grams / 28.3495)
    mm_to_in = 1 / 25.4
    return _ParcelDTO(
        weight_oz=ounces,
        length_in=parcel.length_mm * mm_to_in,
        width_in=parcel.width_mm * mm_to_in,
        height_in=parcel.height_mm * mm_to_in,
    )


def _to_address_dto(address: Address) -> _AddressDTO:
    return _AddressDTO(
        city=address.city,
        region=address.state_or_province,
        postal_code=address.postal_code,
        country_code=address.country_code,
    )


def _post_rates(
    client: httpx.Client, settings: ShipFastSettings, body: _RateRequestDTO
) -> httpx.Response:
    timeout = httpx.Timeout(_TIMEOUT_SECONDS)
    url = f"{settings.SHIPFAST_BASE_URL}/v3/rates"
    try:
        response = client.post(
            url,
            json=body.model_dump(),
            headers=settings.vendor_headers(),
            timeout=timeout,
        )
    except httpx.TimeoutException as exc:
        raise ProviderTimeout("ShipFast request timed out") from exc

    if response.status_code == 429:
        time.sleep(_RETRY_DELAY_SECONDS)
        try:
            response = client.post(
                url,
                json=body.model_dump(),
                headers=settings.vendor_headers(),
                timeout=timeout,
            )
        except httpx.TimeoutException as exc:
            raise ProviderTimeout("ShipFast request timed out") from exc

    return response


def get_quote(parcel: Parcel, destination: Address) -> Quote:
    """Return the cheapest available ground service quote from ShipFast."""
    settings = ShipFastSettings()

    body = _RateRequestDTO(
        account_number=settings.SHIPFAST_ACCOUNT_NUMBER.get_secret_value(),
        parcel=_to_parcel_dto(parcel),
        destination=_to_address_dto(destination),
    )

    with httpx.Client() as client:
        response = _post_rates(client, settings, body)

    if response.status_code == 200:
        parsed = _RateResponseDTO.model_validate(response.json())
        ground_rates = [
            rate for rate in parsed.rates if rate.transit_mode in _GROUND_MODES
        ]
        if not ground_rates:
            raise NoServiceAvailable("No ground service available from ShipFast")

        best = min(
            ground_rates, key=lambda r: (r.amount.value, r.service_level)
        )
        return Quote(
            amount_minor_units=best.amount.value,
            currency=best.amount.currency,
        )

    if response.status_code in (400, 401):
        raise RuntimeError(
            f"ShipFast request failed with status {response.status_code}"
        )

    raise RuntimeError(
        f"ShipFast request failed with status {response.status_code}"
    )
