"""ShipFast connection and credential settings."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ShipFastSettings(BaseSettings):
    """Connection and credential settings for the ShipFast rates API.

    Assembles the complete outbound vendor headers so no caller needs to
    build them or reference an individual header by name.
    """

    model_config = SettingsConfigDict(env_prefix="", frozen=True)

    SHIPFAST_BASE_URL: str
    SHIPFAST_API_KEY: SecretStr
    SHIPFAST_ACCOUNT_NUMBER: SecretStr
    SHIPFAST_SHIPPER_ID: str

    def vendor_headers(self) -> dict[str, str]:
        """Return the complete outbound HTTP header set for ShipFast requests."""
        return {
            "Authorization": f"Bearer {self.SHIPFAST_API_KEY.get_secret_value()}",
            "X-Shipper-Id": self.SHIPFAST_SHIPPER_ID,
        }