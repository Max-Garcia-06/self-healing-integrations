"""ShipFast connection and credential settings."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ShipFastSettings(BaseSettings):
    """Environment-sourced ShipFast connection settings.

    Exposes `vendor_headers()` as the single point of assembly for the
    outbound HTTP header set required by the pinned ShipFast rates API.
    Callers must never assemble headers themselves or reference an
    individual header by name.
    """

    model_config = SettingsConfigDict(env_prefix="SHIPFAST_", frozen=True)

    base_url: str
    api_key: SecretStr
    account_number: SecretStr
    shipper_id: str

    def vendor_headers(self) -> dict[str, str]:
        """Assemble the complete outbound header dict for ShipFast requests.

        Includes every header parameter the pinned OpenAPI spec declares
        as required on the rates operation: `Authorization` and
        `X-Shipper-Id`.
        """
        return {
            "Authorization": f"Bearer {self.api_key.get_secret_value()}",
            "X-Shipper-Id": self.shipper_id,
        }