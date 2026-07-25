"""Call the generated v2/v3 adapter against the running ShipFast mock.

The canonical demo parcel is user_stories/story__cheapest_ground_rate.md:
a 3 lb (1361 g) parcel to Denver, CO 80202. Expected answer: 1240 USD.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.types.shipping import Address, NoServiceAvailable, Parcel, ProviderTimeout
from integrations.shipfast.adapter import get_quote

EXPECTED = 1240

parcel = Parcel(weight_grams=1361, length_mm=300, width_mm=200, height_mm=150)
dest = Address(
    line1="1701 Wynkoop St",
    line2="Suite 200",
    city="Denver",
    state_or_province="CO",
    postal_code="80202",
    country_code="US",
)

try:
    q = get_quote(parcel, dest)
except NoServiceAvailable as e:
    print(f"FAIL  NoServiceAvailable: {e}")
    sys.exit(1)
except ProviderTimeout as e:
    print(f"FAIL  ProviderTimeout: {e}")
    sys.exit(1)
except Exception as e:
    print(f"FAIL  {type(e).__name__}: {e}")
    sys.exit(1)

ok = q.amount_minor_units == EXPECTED and q.currency == "USD"
print(f"{'PASS' if ok else 'FAIL'}  quote = {q.amount_minor_units} {q.currency} "
      f"(expected {EXPECTED} USD)")
sys.exit(0 if ok else 1)
