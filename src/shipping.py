"""Internal domain types shared across every shipping-rate integration.

This module defines the vendor-neutral vocabulary used to request and
represent shipping rate quotes. It performs no network I/O and knows
nothing about any particular carrier's wire format.
"""

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
            raise ValueError("must be a positive integer")
        return value


class Address(BaseModel):
    """Destination attributes needed to request a shipping rate."""

    model_config = ConfigDict(frozen=True)

    country_code: str
    postal_code: str
    city: str
    state_or_province: str | None = None

    @field_validator("country_code")
    @classmethod
    def _validate_country_code(cls, value: str) -> str:
        if len(value) != 2 or not value.isalpha():
            raise ValueError("country_code must be an ISO 3166-1 alpha-2 code")
        return value.upper()

    @field_validator("postal_code", "city")
    @classmethod
    def _must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class Quote(BaseModel):
    """The result of a rate lookup.

    Carries exactly an integer minor-unit value and an ISO 4217 currency
    code. A reader must not be able to tell which carrier produced it.
    """

    model_config = ConfigDict(frozen=True)

    amount_minor_units: int
    currency: str

    @field_validator("currency")
    @classmethod
    def _validate_currency(cls, value: str) -> str:
        if len(value) != 3 or not value.isalpha():
            raise ValueError("currency must be an ISO 4217 code")
        return value.upper()

    @field_validator("amount_minor_units")
    @classmethod
    def _must_be_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("amount_minor_units must not be negative")
        return value


class NoServiceAvailable(Exception):
    """Raised when no carrier can provide a rate for the given shipment."""


class ProviderTimeout(Exception):
    """Raised when a rate lookup does not complete within the allotted time."""