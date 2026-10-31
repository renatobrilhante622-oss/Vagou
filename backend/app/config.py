from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    database_url: str = 'postgresql+asyncpg://vagou:vagou@localhost:5432/vagou'
    jwt_secret: SecretStr
    data_key: SecretStr
    issuer: str = 'vagou-api'
    audience: str = 'vagou-mobile'
    access_minutes: int = Field(default=15, ge=1, le=60)
    redis_url: str = 'redis://localhost:6379/0'
    storage_dir: Path = Path('/tmp/vagou-storage')
    allowed_origins: list[str] = []
    max_pdf_bytes: int = 5 * 1024 * 1024
    privacy_version: str = '2026-01'

    @model_validator(mode='after')
    def validate_keys(self):
        if len(self.jwt_secret.get_secret_value().encode()) < 32:
            raise ValueError('JWT_SECRET must contain at least 32 bytes')
        Fernet(self.data_key.get_secret_value().encode())
        return self


@lru_cache
def settings() -> Settings:
    return Settings()