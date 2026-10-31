from functools import lru_cache
import os
from pathlib import Path
from typing import Literal

from cryptography.fernet import Fernet
from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(Path(__file__).resolve().parents[1] / '.env',
                  Path(__file__).resolve().parents[1] / '.env.smtp.local'),
        extra='ignore', env_ignore_empty=True, hide_input_in_errors=True,
    )
    environment: Literal['development', 'test', 'production'] = Field(default='production', validation_alias=AliasChoices('APP_ENV', 'environment'))
    debug_verification_codes: bool = False
    premium_test_emails: list[str] = Field(default_factory=list)
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
    smtp_host: str = ''
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = Field(default='', validation_alias=AliasChoices('SMTP_USER', 'SMTP_USERNAME', 'smtp_username'))
    smtp_password: SecretStr | None = None
    smtp_from: str = ''
    smtp_security: Literal['starttls', 'ssl'] = 'starttls'
    smtp_timeout_seconds: int = Field(default=15, ge=1, le=60)
    moderator_emails: list[str] = []
    job_source_auto_approve: bool = False
    job_source_urls: list[str] = []
    job_source_allowed_hosts: list[str] = []
    job_source_max_bytes: int = Field(default=2 * 1024 * 1024, ge=1024, le=10 * 1024 * 1024)
    job_source_max_jobs: int = Field(default=200, ge=1, le=1000)
    automation_max_applications_per_run: int = Field(default=20, ge=1, le=100)
    verification_expiry_minutes: int = Field(default=10, ge=5, le=30)
    verification_max_attempts: int = Field(default=5, ge=3, le=10)
    verification_resend_seconds: int = Field(default=60, ge=30, le=3600)
    verification_delivery_timeout_seconds: int = Field(default=5, ge=1, le=10)

    @model_validator(mode='after')
    def validate_keys(self):
        if len(self.jwt_secret.get_secret_value().encode()) < 32:
            raise ValueError('JWT_SECRET must contain at least 32 bytes')
        self.smtp_host = self.smtp_host.strip()
        self.smtp_username = self.smtp_username.strip()
        self.smtp_from = self.smtp_from.strip() or self.smtp_username
        if self.smtp_host.casefold() == 'smtp.gmail.com' and self.smtp_password:
            self.smtp_password = SecretStr(''.join(self.smtp_password.get_secret_value().split()))
        Fernet(self.data_key.get_secret_value().encode())
        return self


@lru_cache
def settings() -> Settings:
    override = os.environ.get('VAGOU_ENV_FILE')
    return Settings(_env_file=override) if override is not None else Settings()
