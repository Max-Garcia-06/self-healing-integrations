
import sys
from pathlib import Path

# Add project root to sys.path to ensure local code is prioritized
# This allows testing local changes without installing the package
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

import pytest
from pydantic import ValidationError

from src.shipping import Parcel, Address, Quote, NoServiceAvailable, ProviderTimeout


def test_parcel_valid_creation():
    p = Parcel(weight_grams=500, length_mm=100, width_mm=50, height_mm=20)
    assert p.weight_grams == 500
    assert p.length_mm == 100
    assert p.width_mm == 50
    assert p.height_mm == 20


@pytest.mark.parametrize("field", ["weight_grams", "length_mm", "width_mm", "height_mm"])
def test_parcel_zero_value_rejected(field):
    kwargs = dict(weight_grams=1, length_mm=1, width_mm=1, height_mm=1)
    kwargs[field] = 0
    with pytest.raises(ValidationError, match=r"positive"):
        Parcel(**kwargs)


@pytest.mark.parametrize("field", ["weight_grams", "length_mm", "width_mm", "height_mm"])
def test_parcel_negative_value_rejected(field):
    kwargs = dict(weight_grams=1, length_mm=1, width_mm=1, height_mm=1)
    kwargs[field] = -5
    with pytest.raises(ValidationError, match=r"positive"):
        Parcel(**kwargs)


def test_parcel_is_frozen():
    p = Parcel(weight_grams=1, length_mm=1, width_mm=1, height_mm=1)
    with pytest.raises(ValidationError):
        p.weight_grams = 100


def test_address_valid_creation():
    a = Address(country_code="us", postal_code="12345", city="Seattle")
    assert a.country_code == "US"
    assert a.postal_code == "12345"
    assert a.city == "Seattle"
    assert a.state_or_province is None


def test_address_state_optional_provided():
    a = Address(
        country_code="US",
        postal_code="12345",
        city="Seattle",
        state_or_province="WA",
    )
    assert a.state_or_province == "WA"


def test_address_country_code_uppercased():
    a = Address(country_code="ca", postal_code="X1X 1X1", city="Toronto")
    assert a.country_code == "CA"


@pytest.mark.parametrize("code", ["USA", "U", "12", ""])
def test_address_invalid_country_code(code):
    with pytest.raises(ValidationError, match=r"country_code|alpha-2"):
        Address(country_code=code, postal_code="12345", city="Seattle")


def test_address_blank_postal_code_rejected():
    with pytest.raises(ValidationError, match=r"blank"):
        Address(country_code="US", postal_code="   ", city="Seattle")


def test_address_blank_city_rejected():
    with pytest.raises(ValidationError, match=r"blank"):
        Address(country_code="US", postal_code="12345", city="")


def test_address_is_frozen():
    a = Address(country_code="US", postal_code="12345", city="Seattle")
    with pytest.raises(ValidationError):
        a.city = "Portland"


def test_quote_has_exactly_two_fields():
    # T3: story__price_in_minor_units.md - Quote carries exactly value + currency
    q = Quote(amount_minor_units=1099, currency="usd")
    assert set(q.model_fields.keys()) == {"amount_minor_units", "currency"}
    assert q.amount_minor_units == 1099
    assert q.currency == "USD"


def test_quote_currency_uppercased():
    q = Quote(amount_minor_units=0, currency="eur")
    assert q.currency == "EUR"


def test_quote_zero_amount_allowed():
    q = Quote(amount_minor_units=0, currency="USD")
    assert q.amount_minor_units == 0


def test_quote_negative_amount_rejected():
    with pytest.raises(ValidationError, match=r"negative"):
        Quote(amount_minor_units=-1, currency="USD")


@pytest.mark.parametrize("currency", ["US", "USDD", "12D", ""])
def test_quote_invalid_currency_rejected(currency):
    with pytest.raises(ValidationError, match=r"currency|ISO 4217"):
        Quote(amount_minor_units=100, currency=currency)


def test_quote_is_frozen():
    q = Quote(amount_minor_units=100, currency="USD")
    with pytest.raises(ValidationError):
        q.amount_minor_units = 200


def test_no_service_available_is_exception():
    assert issubclass(NoServiceAvailable, Exception)
    with pytest.raises(NoServiceAvailable):
        raise NoServiceAvailable("no carrier can service this route")


def test_provider_timeout_is_exception():
    assert issubclass(ProviderTimeout, Exception)
    with pytest.raises(ProviderTimeout):
        raise ProviderTimeout("carrier did not respond in time")