"""Internal domain types shared across shipping-rate integrations."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator


class Parcel(BaseModel):
    """Physical attributes of a package needed to request a shipping rate."""

    model_config = ConfigDict(frozen=True)

    weight_grams: int
    length_mm: int
    width_mm: int
    height_mm: int

    @field_validator("weight_grams", "length_mm", "width_mm", "height_mm")
    @classmethod
    def _must_be_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("must be positive")
        return value


class Address(BaseModel):
    """Destination attributes needed to request a shipping rate."""

    model_config = ConfigDict(frozen=True)

    line1: str | None = None
    line2: str | None = None
    city: str
    state_or_province: str | None = None
    postal_code: str
    country_code: str

    @field_validator("country_code")
    @classmethod
    def _validate_country_code(cls, value: str) -> str:
        if len(value) != 2 or not value.isalpha():
            raise ValueError("country_code must be an ISO 3166-1 alpha-2 code")
        return value.upper()


class Quote(BaseModel):
    """Result of a rate lookup, carrier-agnostic."""

    model_config = ConfigDict(frozen=True)

    amount_minor_units: int
    currency: str

    @field_validator("currency")
    @classmethod
    def _validate_currency(cls, value: str) -> str:
        if len(value) != 3 or not value.isalpha():
            raise ValueError("currency must be an ISO 4217 code")
        return value.upper()


class NoServiceAvailable(Exception):
    """Raised when no shipping service can fulfil the requested parcel/route."""


class ProviderTimeout(Exception):
    """Raised when a rate lookup does not complete in time."""