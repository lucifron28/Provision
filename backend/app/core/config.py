from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Provision Household Inventory API"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: Literal["development", "test", "production"] = "development"
    DATABASE_URL: str = "postgresql+psycopg://provision:provision@127.0.0.1:5432/provision"
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    # Server-side provider remains disabled until explicitly enabled.
    DEEPSEEK_API_KEY: SecretStr | None = None
    DEEPSEEK_ENABLED: bool = False
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-flash"
    DEEPSEEK_THINKING_MODE: Literal["disabled", "enabled"] = "disabled"
    DEEPSEEK_TIMEOUT_SECONDS: float = Field(default=15, gt=0, le=120)
    DEEPSEEK_MAX_OUTPUT_TOKENS: int = Field(default=1024, ge=1, le=8192)
    DEEPSEEK_MAX_PROMPT_CHARACTERS: int = Field(default=24000, ge=1, le=200000)
    DEEPSEEK_REQUESTS_PER_MINUTE: int = Field(default=10, ge=1, le=1000)
    DEEPSEEK_REQUEST_BUDGET: int = Field(default=100, ge=1, le=10000)
    DEEPSEEK_HOUSEHOLD_REQUEST_BUDGET: int = Field(default=50, ge=1, le=10000)
    DEEPSEEK_MAX_RESPONSE_BYTES: int = Field(default=1000000, ge=1024, le=20000000)
    DEEPSEEK_MAX_SEARCH_RESULTS: int = Field(default=10, ge=1, le=50)
    DEEPSEEK_MAX_FETCH_CHARACTERS: int = Field(default=50000, ge=1, le=500000)

    @field_validator("DEEPSEEK_BASE_URL")
    @classmethod
    def validate_deepseek_base_url(cls, value: str) -> str:
        parts = urlsplit(value.strip())
        if (
            parts.scheme.lower() != "https"
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or "\\" in parts.netloc
            or any(char.isspace() for char in parts.netloc)
            or parts.path not in {"", "/"}
            or parts.query
            or parts.fragment
        ):
            raise ValueError("DeepSeek base URL must be an HTTPS origin without credentials or path")
        try:
            _ = parts.port
        except ValueError as exc:
            raise ValueError("DeepSeek base URL has an invalid port") from exc
        return f"https://{parts.netloc}"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
