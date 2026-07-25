"""ShipFast connection and credential settings.

Hand-written rather than regenerated: configuration is a deployment concern,
not part of the surface a vendor wire-format change rewrites. Keeping it
outside the regenerated blast radius is what lets a new required header be
absorbed by config instead of by a prompt edit.
"""

from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ShipFastSettings(BaseSettings):
    """Connection and credential settings for the ShipFast provider.

    Callers never assemble outbound headers themselves and never reference an
    individual header by name; they ask for the complete set via
    :meth:`vendor_headers`.
    """

    model_config = SettingsConfigDict(
        env_prefix="SHIPFAST_",
        env_file=".env",
        extra="ignore",
        frozen=True,
    )

    base_url: str = "http://localhost:8081"
    api_key: SecretStr = SecretStr("")
    account_number: SecretStr = SecretStr("")
    shipper_id: str = ""

    def vendor_headers(self) -> dict[str, str]:
        """Return the complete outbound header set for a provider request.

        This is the only place provider headers are named. Adding a header the
        provider newly requires is a change here, never a change to any prompt.
        """
        return {
            "Authorization": f"Bearer {self.api_key.get_secret_value()}",
            "X-Shipper-Id": self.shipper_id,
            "Content-Type": "application/json",
        }

    def account_number_value(self) -> str:
        """Return the account number for inclusion in a request body."""
        return self.account_number.get_secret_value()
