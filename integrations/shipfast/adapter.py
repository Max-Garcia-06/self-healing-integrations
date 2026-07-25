"""ShipFast shipping-rate adapter."""
from __future__ import annotations

import time

import httpx
from pydantic import BaseModel, ConfigDict

from src.config.shipfast import ShipFastSettings
from src.types.shipping import Address, NoServiceAvailable, Parcel, ProviderTimeout, Quote

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


def _grams_to_oz(grams: int) -> int:
    return round(grams / 28.349523125)


def _mm_to_in(mm: int) -> float:
    return mm / 25.4


def _build_request(parcel: Parcel, destination: Address, account_number: str) -> _RateRequestDTO:
    return _RateRequestDTO(
        account_number=account_number,
        parcel=_ParcelDTO(
            weight_oz=_grams_to_oz(parcel.weight_grams),
            length_in=_mm_to_in(parcel.length_mm),
            width_in=_mm_to_in(parcel.width_mm),
            height_in=_mm_to_in(parcel.height_mm),
        ),
        destination=_AddressDTO(
            line1=destination.line1,
            line2=destination.line2,
            city=destination.city,
            region=destination.state_or_province,
            postal_code=destination.postal_code,
            country_code=destination.country_code,
        ),
    )


def get_quote(parcel: Parcel, destination: Address) -> Quote:
    """Translate parcel/destination into a ShipFast rate request and return the cheapest ground quote."""
    settings = ShipFastSettings()
    request_dto = _build_request(
        parcel, destination, settings.shipfast_account_number.get_secret_value()
    )
    url = f"{settings.shipfast_base_url}/v3/rates"
    headers = settings.vendor_headers()
    timeout = httpx.Timeout(_TIMEOUT_SECONDS)

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                url, headers=headers, json=request_dto.model_dump(mode="json")
            )
            if response.status_code == 429:
                time.sleep(_RETRY_DELAY_SECONDS)
                response = client.post(
                    url, headers=headers, json=request_dto.model_dump(mode="json")
                )
    except httpx.TimeoutException as exc:
        raise ProviderTimeout("ShipFast request timed out") from exc

    if response.status_code != 200:
        raise httpx.HTTPStatusError(
            f"ShipFast returned status {response.status_code}",
            request=response.request,
            response=response,
        )

    parsed = _RateResponseDTO.model_validate(response.json())

    ground_rates = [rate for rate in parsed.rates if rate.transit_mode in _GROUND_MODES]
    if not ground_rates:
        raise NoServiceAvailable("No ground service available")

    cheapest = min(ground_rates, key=lambda r: (r.amount.value, r.service_level))

    return Quote(
        amount_minor_units=cheapest.amount.value,
        currency=cheapest.amount.currency,
    )