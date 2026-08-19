import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


def to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class ContractModel(BaseModel):
    """Strict JSON contract with camel-case aliases for browser clients."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
    )


Identifier = Annotated[
    str,
    Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]
ShortText = Annotated[str, Field(min_length=1, max_length=255)]
LabelText = Annotated[str, Field(min_length=1, max_length=5_000)]
Confidence = Annotated[float, Field(ge=0, le=1)]
NormalizedCoordinate = Annotated[float, Field(ge=0, le=1)]
DurationMilliseconds = Annotated[int, Field(ge=0)]


def is_sha256(value: str) -> bool:
    return re.fullmatch(r"[a-fA-F0-9]{64}", value) is not None
