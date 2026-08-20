from functools import lru_cache

from app.config import get_settings
from app.extraction.providers import (
    MockOcrExtractor,
    OcrExtractor,
    OpenAiOcrExtractor,
    UnconfiguredOpenAiExtractor,
)


@lru_cache
def get_ocr_extractor() -> OcrExtractor:
    settings = get_settings()
    if settings.ocr_provider == "mock":
        return MockOcrExtractor()
    if settings.openai_api_key is None:
        return UnconfiguredOpenAiExtractor(model=settings.openai_ocr_model)
    return OpenAiOcrExtractor(
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.openai_ocr_model,
        image_detail=settings.openai_image_detail,
        timeout_seconds=settings.openai_ocr_timeout_seconds,
    )
