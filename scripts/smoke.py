"""Smoke test: call get_quote against the running mock upstream."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.shipping import Parcel, Address, NoServiceAvailable, ProviderTimeout
from src.shipfast_adapter import get_quote

parcel = Parcel(weight_grams=1361, length_mm=300, width_mm=200, height_mm=150)  # ~3 lb
dest = Address(country_code="US", postal_code="80202", city="Denver", state_or_province="CO")

try:
    q = get_quote(parcel, dest)
    print(f"PASS  Quote = {q.amount_minor_units} {q.currency}")
except NoServiceAvailable as e:
    print(f"NoServiceAvailable: {e}")
except ProviderTimeout as e:
    print(f"ProviderTimeout: {e}")
except Exception as e:
    print(f"FAIL  {type(e).__name__}: {e}")
    raise
