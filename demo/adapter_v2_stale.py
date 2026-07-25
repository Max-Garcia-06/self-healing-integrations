"""ShipFast shipping-rate adapter."""
from __future__ import annotations

import time

import httpx
from pydantic import BaseModel, ConfigDict

from src.config.shipfast import ShipFastSettings
from src.types.shipping import Address, NoServiceAvailable, Parcel, ProviderTimeout, Quote

_TIMEOUT_SECONDS = 3.0
_RETRY_DELAY_SECONDS = 0.2
_GROUND_MODES = frozenset({"surface", "ground"})
_GRAMS_PER_OUNCE = 28.349523125
_MM_PER_INCH = 25.4


class _ParcelDTO(BaseModel):
    model_config = ConfigDict(frozen=True)
    weight_oz: int
    length_in: float
    width_in: float
    height_in: float


class _AddressDTO(BaseModel):
    model_config = ConfigDict(frozen=True)
    line1: str | None = None
    line2: str | None = None
    city: str | None = None
    region: str | None = None
    postal_code: str
    country_code: str


class _RateRequestDTO(BaseModel):
    model_config = ConfigDict(frozen=True)
    account_number: str
    parcel: _ParcelDTO
    destination: _AddressDTO


class _RateDTO(BaseModel):
    model_config = ConfigDict(frozen=True)
    service_code: str
    service_name: str
    transit_mode: str
    price_cents: int
    currency: str
    estimated_days: int | None = None


class _RateResponseDTO(BaseModel):
    model_config = ConfigDict(frozen=True)
    request_id: str | None = None
    rates: list[_RateDTO] = []


def _to_parcel_dto(parcel: Parcel) -> _ParcelDTO:
    weight_oz = round(parcel.weight_grams / _GRAMS_PER_OUNCE)
    return _ParcelDTO(
        weight_oz=weight_oz,
        length_in=parcel.length_mm / _MM_PER_INCH,
        width_in=parcel.width_mm / _MM_PER_INCH,
        height_in=parcel.height_mm / _MM_PER_INCH,
    )


def _to_address_dto(destination: Address) -> _AddressDTO:
    return _AddressDTO(
        line1=destination.line1,
        line2=destination.line2,
        city=destination.city,
        region=destination.state_or_province,
        postal_code=destination.postal_code,
        country_code=destination.country_code,
    )


def _send_request(
    client: httpx.Client, url: str, headers: dict[str, str], body: dict
) -> httpx.Response:
    try:
        response = client.post(url, headers=headers, json=body)
    except httpx.TimeoutException as exc:
        raise ProviderTimeout("ShipFast rate request timed out") from exc

    if response.status_code == 429:
        time.sleep(_RETRY_DELAY_SECONDS)
        try:
            response = client.post(url, headers=headers, json=body)
        except httpx.TimeoutException as exc:
            raise ProviderTimeout("ShipFast rate request timed out") from exc

    return response


def get_quote(parcel: Parcel, destination: Address) -> Quote:
    """Get the cheapest ground shipping quote from ShipFast for this parcel and destination."""
    settings = ShipFastSettings()

    request_dto = _RateRequestDTO(
        account_number=settings.account_number.get_secret_value(),
        parcel=_to_parcel_dto(parcel),
        destination=_to_address_dto(destination),
    )

    url = f"{settings.base_url}/v2/rates"
    headers = settings.vendor_headers()
    timeout = httpx.Timeout(_TIMEOUT_SECONDS)

    with httpx.Client(timeout=timeout) as client:
        response = _send_request(
            client, url, headers, request_dto.model_dump(mode="json")
        )

    if response.status_code != 200:
        raise httpx.HTTPStatusError(
            f"ShipFast rate request failed with status {response.status_code}",
            request=response.request,
            response=response,
        )

    rate_response = _RateResponseDTO.model_validate(response.json())

    ground_rates = [r for r in rate_response.rates if r.transit_mode in _GROUND_MODES]

    if not ground_rates:
        raise NoServiceAvailable("No ground shipping service available from ShipFast")

    cheapest = min(ground_rates, key=lambda r: (r.price_cents, r.service_code))

    return Quote(amount_minor_units=cheapest.price_cents, currency=cheapest.currency)