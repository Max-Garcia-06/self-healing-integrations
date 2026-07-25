"""ShipFast connection settings.

Reads ShipFast connection and credential settings from the environment and
exposes them as a single settings object. Assembles the complete outbound
vendor header set in one place so callers never need to know individual
header names.
"""

from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ShipFastSettings(BaseSettings):
    """Connection and credential settings for the ShipFast provider.

    Values are read from the environment. Credentials are stored as
    `SecretStr` so they are never accidentally logged or serialized.
    """

    model_config = SettingsConfigDict(
        env_prefix="SHIPFAST_",
        frozen=True,
    )

    base_url: str
    api_key: SecretStr
    account_number: SecretStr
    shipper_id: str

    def vendor_headers(self) -> dict[str, str]:
        """Assemble the complete outbound HTTP header set for ShipFast.

        Per the pinned ShipFast Rates API spec, the only header required to
        authenticate a request is `Authorization`, carrying a bearer token
        built from the API key. This is the sole place in the codebase that
        knows this header name; callers must never reference it directly.
        """
        return {
            "Authorization": f"Bearer {self.api_key.get_secret_value()}",
        }