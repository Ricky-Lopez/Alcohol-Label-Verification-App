from typing import Annotated

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from app.comparison import compare
from app.models.verification import (
    ComparisonInput,
    ComparisonRequest,
    RulesetReference,
    VerificationResult,
)
from app.rules import (
    PROTOTYPE_RULESET_EFFECTIVE_DATE,
    PROTOTYPE_RULESET_ID,
    PROTOTYPE_RULESET_VERSION,
)

router = APIRouter(prefix="/api", tags=["comparison"])


def active_ruleset() -> RulesetReference:
    return RulesetReference(
        ruleset_id=PROTOTYPE_RULESET_ID,
        version=PROTOTYPE_RULESET_VERSION,
        effective_date=PROTOTYPE_RULESET_EFFECTIVE_DATE,
        source_uri="docs/REQUIREMENTS.md#fr-016",
    )


@router.post("/comparisons", response_model=VerificationResult)
async def create_comparison(request: Annotated[ComparisonRequest, ...]) -> VerificationResult:
    try:
        comparison = ComparisonInput(
            comparison_id=request.comparison_id,
            application=request.submission.application,
            images=request.submission.images,
            extraction=request.extraction,
            ruleset=active_ruleset(),
        )
    except ValidationError as error:
        raise HTTPException(
            status_code=422, detail="The comparison request is inconsistent."
        ) from error
    return compare(comparison)
