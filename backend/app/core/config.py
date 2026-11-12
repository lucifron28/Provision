from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

from app.core.migration_safety import validate_staging_database_urls


LOCAL_DATABASE_URL = "postgresql+psycopg://provision:provision@127.0.0.1:5432/provision"


def _validated_database_url(value: str, setting_name: str) -> str:
    try:
        parsed = make_url(value.strip())
    except Exception as exc:
        raise ValueError(f"{setting_name} must be a valid SQLAlchemy database URL") from exc

    if parsed.get_backend_name() == "sqlite":
        return value.strip()
    if parsed.drivername != "postgresql+psycopg" or not parsed.host or not parsed.database:
        raise ValueError(f"{setting_name} must use PostgreSQL with psycopg 3 and include a host and database")
    return value.strip()


def _requires_tls(value: str) -> bool:
    parsed = make_url(value)
    if parsed.get_backend_name() != "postgresql":
        return False
    host = (parsed.host or "").strip("[]").lower()
    if host in {"localhost", "127.0.0.1", "::1"}:
        return False
    try:
        from ipaddress import ip_address

        if ip_address(host).is_loopback:
            return False
    except ValueError:
        pass
    sslmode = parsed.query.get("sslmode")
    if isinstance(sslmode, (list, tuple)):
        sslmode = sslmode[0] if sslmode else None
    return sslmode in {"require", "verify-ca", "verify-full"}


class PublisherPacingSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min_interval_seconds: float = Field(default=0.1, ge=0.001, le=3600, allow_inf_nan=False)
    window_seconds: int = Field(default=60, ge=1, le=86400)
    window_requests: int = Field(default=60, ge=1, le=10000)


class Settings(BaseSettings):
    PROJECT_NAME: str = "Provision Household Inventory API"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: Literal["development", "test", "production"] = "development"
    DEPLOYMENT_ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    STAGING_TEST_FIXTURES_ENABLED: bool = False
    STAGING_TEST_FIXTURE_TOKEN: SecretStr | None = None
    DATABASE_URL: str = Field(default=LOCAL_DATABASE_URL, repr=False)
    MIGRATION_DATABASE_URL: SecretStr | None = None
    JWT_SECRET_KEY: str = Field(repr=False, min_length=1)
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
    MEALDB_ENABLED: bool = False
    MEALDB_REQUEST_BUDGET: int = Field(default=100, ge=1, le=10000)
    MEALDB_MIN_INTERVAL_SECONDS: int = Field(default=2, ge=1, le=3600)
    WIKIBOOKS_ENABLED: bool = False
    PUBLISHER_PACING_DEFAULT: PublisherPacingSettings = Field(default_factory=PublisherPacingSettings)
    PUBLISHER_PACING_OVERRIDES: dict[str, PublisherPacingSettings] = Field(default_factory=dict)
    PUBLISHER_MAX_COOLDOWN_SECONDS: int = Field(default=3600, ge=1, le=86400)

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        return _validated_database_url(value, "DATABASE_URL")

    @field_validator("MIGRATION_DATABASE_URL", mode="before")
    @classmethod
    def validate_migration_database_url(cls, value: str | SecretStr | None) -> str | None:
        if value is None:
            return None
        raw_value = value.get_secret_value() if isinstance(value, SecretStr) else value
        validated = _validated_database_url(raw_value, "MIGRATION_DATABASE_URL")
        if make_url(validated).get_backend_name() != "postgresql":
            raise ValueError("MIGRATION_DATABASE_URL must use PostgreSQL")
        if "-pooler." in (make_url(validated).host or ""):
            raise ValueError("MIGRATION_DATABASE_URL must use a direct PostgreSQL endpoint")
        return validated

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def validate_jwt_secret(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("JWT_SECRET_KEY must not be empty")
        return value

    @model_validator(mode="after")
    def validate_deployment_configuration(self):
        if self.DEPLOYMENT_ENVIRONMENT in {"staging", "production"} and self.ENVIRONMENT != "production":
            raise ValueError("Hosted deployments must use ENVIRONMENT=production")
        if self.DEPLOYMENT_ENVIRONMENT == "staging":
            if self.MIGRATION_DATABASE_URL is None:
                raise ValueError("MIGRATION_DATABASE_URL is required for staging")
            validate_staging_database_urls(
                self.DATABASE_URL,
                self.MIGRATION_DATABASE_URL.get_secret_value(),
            )
        if self.STAGING_TEST_FIXTURES_ENABLED:
            if self.DEPLOYMENT_ENVIRONMENT != "staging":
                raise ValueError("Staging test fixtures may only be enabled in a staging deployment")
            if self.STAGING_TEST_FIXTURE_TOKEN is None or not self.STAGING_TEST_FIXTURE_TOKEN.get_secret_value().strip():
                raise ValueError("STAGING_TEST_FIXTURE_TOKEN is required when staging fixtures are enabled")
        if self.ENVIRONMENT == "production":
            if self.DATABASE_URL == LOCAL_DATABASE_URL:
                raise ValueError("DATABASE_URL must be explicitly configured for production")
            if make_url(self.DATABASE_URL).get_backend_name() != "postgresql":
                raise ValueError("Production DATABASE_URL must use PostgreSQL")
            if len(self.JWT_SECRET_KEY) < 32:
                raise ValueError("Production JWT_SECRET_KEY must contain at least 32 characters")
            if not _requires_tls(self.DATABASE_URL):
                raise ValueError("Remote production DATABASE_URL must require TLS")
            if self.MIGRATION_DATABASE_URL is not None and not _requires_tls(
                self.MIGRATION_DATABASE_URL.get_secret_value()
            ):
                raise ValueError("Remote MIGRATION_DATABASE_URL must require TLS")
        return self

    @field_validator("PUBLISHER_PACING_OVERRIDES")
    @classmethod
    def validate_publisher_hosts(cls, value):
        from app.services.source_urls import normalize_host
        if any(normalize_host(host) != host for host in value):
            raise ValueError("Publisher pacing override hosts must be canonical")
        return value

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
        hide_input_in_errors=True,
    )


settings = Settings()
