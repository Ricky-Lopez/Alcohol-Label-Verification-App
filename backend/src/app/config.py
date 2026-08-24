from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_environment: Literal["development", "test", "production"] = "development"
    ocr_provider: Literal["openai", "mock"] = "openai"
    openai_api_key: SecretStr | None = None
    openai_ocr_model: str = "gpt-4o-mini"
    openai_image_detail: Literal["low", "high", "auto"] = "high"
    openai_ocr_timeout_seconds: Annotated[float, Field(gt=0, le=300)] = 300.0
    frontend_dist_dir: Path = REPOSITORY_ROOT / "frontend" / "dist"

    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def prevent_production_mock_provider(self) -> "Settings":
        if self.app_environment == "production" and self.ocr_provider == "mock":
            raise ValueError("the mock OCR provider cannot run in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
