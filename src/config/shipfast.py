"""ShipFast connection settings."""

from pydantic import SecretStr, ConfigDict
from pydantic_settings import BaseSettings, SettingsConfigDict


class ShipFastSettings(BaseSettings):
    """Connection and credential settings for the ShipFast carrier API."""

    model_config = SettingsConfigDict(
        env_prefix="SHIPFAST_",
        frozen=True,
    )

    base_url: str
    api_key: SecretStr
    account_number: SecretStr
    shipper_id: str

    def vendor_headers(self) -> dict[str, str]:
        """Assemble the complete outbound HTTP header set for ShipFast requests."""
        return {
            "Authorization": f"Bearer {self.api_key.get_secret_value()}",
            "X-ShipFast-Account-Number": self.account_number.get_secret_value(),
            "X-ShipFast-Shipper-Id": self.shipper_id,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }