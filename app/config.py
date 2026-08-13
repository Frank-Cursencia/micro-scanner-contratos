from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración por variables de entorno, sin secretos hardcodeados."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    service_name: str = "micro-scanner-contratos"
    service_version: str = "0.1.0"
    environment: str = "development"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 4012

    microservice_token: str | None = Field(default=None, repr=False)

    gemini_api_key: str | None = Field(default=None, repr=False)
    gemini_model: str = "gemini-2.5-flash"

    max_file_size_mb: int = 15

    @field_validator("microservice_token", "gemini_api_key")
    @classmethod
    def blank_to_none(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return value

    @property
    def is_service_token_configured(self) -> bool:
        return self.microservice_token is not None


@lru_cache
def get_settings() -> Settings:
    return Settings()
