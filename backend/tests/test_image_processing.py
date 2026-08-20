from io import BytesIO

import pytest
from PIL import Image

import app.extraction.image_processing as image_processing
from app.extraction.image_processing import InvalidImageError, prepare_image
from app.models.label import ImageMediaType, LabelImageInput


def encode_image(
    *,
    image_format: str = "PNG",
    size: tuple[int, int] = (100, 50),
    exif: Image.Exif | None = None,
) -> bytes:
    output = BytesIO()
    save_options = {"exif": exif} if exif is not None else {}
    Image.new("RGB", size, "white").save(
        output,
        format=image_format,
        **save_options,
    )
    return output.getvalue()


def metadata_for(data: bytes, *, media_type: ImageMediaType, file_name: str) -> LabelImageInput:
    return LabelImageInput(
        client_image_id="image-test-001",
        file_name=file_name,
        media_type=media_type,
        size_bytes=len(data),
    )


def test_prepare_image_resizes_large_jpeg_without_upscaling() -> None:
    data = encode_image(image_format="JPEG", size=(3000, 1000))
    metadata = metadata_for(data, media_type=ImageMediaType.JPEG, file_name="label.jpg")

    prepared = prepare_image(
        metadata,
        upload_file_name="label.jpg",
        upload_media_type="image/jpeg",
        data=data,
    )

    assert prepared.media_type == "image/jpeg"
    assert prepared.width == 2048
    assert prepared.height == 683
    with Image.open(BytesIO(prepared.data)) as image:
        assert image.format == "JPEG"
        assert image.info.get("exif") is None


def test_prepare_image_applies_exif_orientation() -> None:
    exif = Image.Exif()
    exif[274] = 6
    data = encode_image(image_format="JPEG", size=(20, 10), exif=exif)
    metadata = metadata_for(data, media_type=ImageMediaType.JPEG, file_name="rotated.jpg")

    prepared = prepare_image(
        metadata,
        upload_file_name="rotated.jpg",
        upload_media_type="image/jpeg",
        data=data,
    )

    assert (prepared.width, prepared.height) == (10, 20)


def test_prepare_image_preserves_png_until_processed_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    data = encode_image()
    metadata = metadata_for(data, media_type=ImageMediaType.PNG, file_name="label.png")

    prepared = prepare_image(
        metadata,
        upload_file_name="label.png",
        upload_media_type="image/png",
        data=data,
    )
    assert prepared.media_type == "image/png"

    monkeypatch.setattr(image_processing, "MAX_PNG_OUTPUT_BYTES", 1)
    converted = prepare_image(
        metadata,
        upload_file_name="label.png",
        upload_media_type="image/png",
        data=data,
    )
    assert converted.media_type == "image/jpeg"


@pytest.mark.parametrize(
    ("data", "file_name", "upload_media_type", "expected_message"),
    [
        (b"", "label.png", "image/png", "empty"),
        (b"not an image", "label.png", "image/png", "not a readable"),
    ],
)
def test_prepare_image_rejects_invalid_content(
    data: bytes,
    file_name: str,
    upload_media_type: str,
    expected_message: str,
) -> None:
    metadata = metadata_for(
        data or b"x",
        media_type=ImageMediaType.PNG,
        file_name=file_name,
    )
    if not data:
        metadata = metadata.model_copy(update={"size_bytes": 1})

    with pytest.raises(InvalidImageError, match=expected_message):
        prepare_image(
            metadata,
            upload_file_name=file_name,
            upload_media_type=upload_media_type,
            data=data,
        )


def test_prepare_image_rejects_metadata_and_content_mismatches() -> None:
    data = encode_image(image_format="JPEG")
    metadata = metadata_for(data, media_type=ImageMediaType.PNG, file_name="label.png")

    with pytest.raises(InvalidImageError, match="content does not match"):
        prepare_image(
            metadata,
            upload_file_name="label.png",
            upload_media_type="image/png",
            data=data,
        )

    with pytest.raises(InvalidImageError, match="filename does not match"):
        prepare_image(
            metadata.model_copy(update={"media_type": ImageMediaType.JPEG}),
            upload_file_name="other.jpg",
            upload_media_type="image/jpeg",
            data=data,
        )


def test_prepare_image_enforces_decoded_pixel_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    data = encode_image(size=(3, 2))
    metadata = metadata_for(data, media_type=ImageMediaType.PNG, file_name="label.png")
    monkeypatch.setattr(image_processing, "MAX_IMAGE_PIXELS", 5)

    with pytest.raises(InvalidImageError, match="dimensions are not supported"):
        prepare_image(
            metadata,
            upload_file_name="label.png",
            upload_media_type="image/png",
            data=data,
        )
