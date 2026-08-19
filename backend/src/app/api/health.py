from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

SERVICE_NAME = "alcohol-label-verification-api"

router = APIRouter(tags=["operations"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service=SERVICE_NAME)
