"""ShipFast connection settings."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ShipFastSettings(BaseSettings):
    """Connection and credential settings for the ShipFast provider.

    Reads configuration from the environment and exposes a single method
    to assemble the complete outbound headers for ShipFast requests, so
    no caller needs to build or reference individual headers itself.
    """

    model_config = SettingsConfigDict(frozen=True)

    shipfast_base_url: str
    shipfast_api_key: SecretStr
    shipfast_account_number: SecretStr
    shipfast_shipper_id: str

    def vendor_headers(self) -> dict[str, str]:
        """Assemble the complete outbound HTTP header set for ShipFast."""
        return {
            "Authorization": f"Bearer {self.shipfast_api_key.get_secret_value()}",
            "X-Shipper-Id": self.shipfast_shipper_id,
        }