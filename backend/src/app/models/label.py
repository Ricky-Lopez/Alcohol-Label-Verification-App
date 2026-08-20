from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.models.base import ContractModel, Identifier, LabelText, ShortText, is_sha256


class BeverageType(StrEnum):
    BEER = "beer"
    WINE = "wine"
    DISTILLED_SPIRITS = "distilled_spirits"


class IntakeSource(StrEnum):
    PRELOADED = "preloaded"
    AD_HOC = "ad_hoc"
    BATCH = "batch"


class ResponsiblePartyRole(StrEnum):
    BOTTLER = "bottler"
    PRODUCER = "producer"
    DISTILLER = "distiller"
    BREWER = "brewer"
    WINERY = "winery"
    IMPORTER = "importer"
    PACKER = "packer"
    OTHER = "other"


class NetContentsUnit(StrEnum):
    MILLILITER = "mL"
    LITER = "L"
    FLUID_OUNCE = "fl_oz"
    PINT = "pt"
    QUART = "qt"
    GALLON = "gal"


class LabelPanelType(StrEnum):
    BRAND = "brand"
    BACK = "back"
    SIDE = "side"
    NECK = "neck"
    OTHER = "other"
    UNKNOWN = "unknown"


class ImageMediaType(StrEnum):
    JPEG = "image/jpeg"
    PNG = "image/png"


class StatementType(StrEnum):
    SULFITES = "sulfites"
    COLOR_ADDITIVE = "color_additive"
    ASPARTAME = "aspartame"
    AGE = "age"
    STATEMENT_OF_COMPOSITION = "statement_of_composition"
    FOREIGN_WINE_PERCENTAGE = "foreign_wine_percentage"
    OTHER = "other"


class PostalAddress(ContractModel):
    street_lines: Annotated[list[ShortText], Field(default_factory=list, max_length=4)]
    city: ShortText
    region: ShortText | None = None
    postal_code: Annotated[str, Field(min_length=1, max_length=32)] | None = None
    country_code: Annotated[str, Field(pattern=r"^[A-Z]{2}$")]


class ResponsibleParty(ContractModel):
    role: ResponsiblePartyRole
    name: ShortText
    address: PostalAddress
    statement_prefix: Annotated[str, Field(min_length=1, max_length=100)] | None = None


class AlcoholContent(ContractModel):
    abv_percent: Annotated[float, Field(ge=0, le=100)]
    proof: Annotated[float, Field(ge=0, le=200)] | None = None
    expected_display_text: ShortText | None = None


class NetContents(ContractModel):
    value: Annotated[float, Field(gt=0)]
    unit: NetContentsUnit
    expected_display_text: ShortText | None = None


class CountryOfOrigin(ContractModel):
    country_code: Annotated[str, Field(pattern=r"^[A-Z]{2}$")]
    display_name: ShortText


class ExpectedStatement(ContractModel):
    statement_type: StatementType
    expected_text: LabelText
    rule_reference: ShortText | None = None


class ExpectedLabelFields(ContractModel):
    brand_name: ShortText
    class_type_designation: ShortText
    alcohol_content: AlcoholContent | None = None
    net_contents: NetContents
    responsible_parties: Annotated[list[ResponsibleParty], Field(min_length=1)]
    country_of_origin: CountryOfOrigin | None = None
    appellation_of_origin: ShortText | None = None
    additional_required_statements: list[ExpectedStatement] = Field(default_factory=list)


class ApplicationRecord(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    record_id: Identifier
    intake_source: IntakeSource
    beverage_type: BeverageType
    imported: bool
    expected_label: ExpectedLabelFields

    @model_validator(mode="after")
    def validate_conditional_fields(self) -> "ApplicationRecord":
        if self.imported and self.expected_label.country_of_origin is None:
            raise ValueError("countryOfOrigin is required for imported products")

        if (
            self.beverage_type == BeverageType.DISTILLED_SPIRITS
            and self.expected_label.alcohol_content is None
        ):
            raise ValueError("alcoholContent is required for distilled spirits")

        return self


class LabelImageInput(ContractModel):
    client_image_id: Identifier
    file_name: Annotated[str, Field(min_length=1, max_length=255)]
    media_type: ImageMediaType
    size_bytes: Annotated[int, Field(gt=0, le=20_000_000)]
    panel_type: LabelPanelType = LabelPanelType.UNKNOWN
    sha256: Annotated[str, Field(min_length=64, max_length=64)] | None = None

    @model_validator(mode="after")
    def validate_sha256(self) -> "LabelImageInput":
        if self.sha256 is not None and not is_sha256(self.sha256):
            raise ValueError("sha256 must be a 64-character hexadecimal digest")
        return self


class VerificationSubmission(ContractModel):
    submission_id: Identifier
    application: ApplicationRecord
    images: Annotated[list[LabelImageInput], Field(min_length=1, max_length=12)]

    @model_validator(mode="after")
    def validate_unique_images(self) -> "VerificationSubmission":
        image_ids = [image.client_image_id for image in self.images]
        if len(image_ids) != len(set(image_ids)):
            raise ValueError("clientImageId values must be unique within a submission")
        return self


class SubmissionTransport(ContractModel):
    """Documents the multipart boundary without embedding image bytes in JSON."""

    application_part: Literal["submission"] = "submission"
    file_part: Literal["images"] = "images"
    encoding: Literal["multipart/form-data"] = "multipart/form-data"
