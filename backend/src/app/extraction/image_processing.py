from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from app.models.label import ImageMediaType, LabelImageInput

MAX_UPLOAD_BYTES = 20_000_000
MAX_IMAGE_PIXELS = 40_000_000
MAX_LONG_EDGE = 2048
MAX_PNG_OUTPUT_BYTES = 4_000_000


class InvalidImageError(ValueError):
    """Safe validation error for an uploaded image."""


@dataclass(frozen=True, slots=True)
class PreparedImage:
    client_image_id: str
    source_file_name: str
    media_type: str
    data: bytes
    width: int
    height: int


def _flatten_to_rgb(image: Image.Image) -> Image.Image:
    if image.mode == "RGB":
        return image
    if "A" in image.getbands():
        background = Image.new("RGB", image.size, "white")
        background.paste(image, mask=image.getchannel("A"))
        return background
    return image.convert("RGB")


def _encode_png(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def _encode_jpeg(image: Image.Image, *, quality: int) -> bytes:
    output = BytesIO()
    _flatten_to_rgb(image).save(
        output,
        format="JPEG",
        quality=quality,
        optimize=True,
        subsampling=0,
    )
    return output.getvalue()


def prepare_image(
    metadata: LabelImageInput,
    *,
    upload_file_name: str | None,
    upload_media_type: str | None,
    data: bytes,
) -> PreparedImage:
    if not data:
        raise InvalidImageError("The uploaded image is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise InvalidImageError("The uploaded image exceeds the 20 MB limit.")
    if metadata.size_bytes != len(data):
        raise InvalidImageError("The uploaded image size does not match its metadata.")
    if upload_file_name != metadata.file_name:
        raise InvalidImageError("The uploaded image filename does not match its metadata.")
    if upload_media_type != metadata.media_type.value:
        raise InvalidImageError("The uploaded image media type does not match its metadata.")

    try:
        with Image.open(BytesIO(data)) as source:
            actual_format = source.format
            if getattr(source, "is_animated", False):
                raise InvalidImageError("Animated images are not supported.")
            width, height = source.size
            if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
                raise InvalidImageError("The uploaded image dimensions are not supported.")

            expected_format = {
                ImageMediaType.JPEG: "JPEG",
                ImageMediaType.PNG: "PNG",
            }[metadata.media_type]
            if actual_format != expected_format:
                raise InvalidImageError("The uploaded image content does not match its media type.")

            source.load()
            normalized = ImageOps.exif_transpose(source)
            normalized.thumbnail((MAX_LONG_EDGE, MAX_LONG_EDGE), Image.Resampling.LANCZOS)
            normalized = normalized.copy()
    except InvalidImageError:
        raise
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError) as error:
        raise InvalidImageError("The uploaded file is not a readable JPEG or PNG image.") from error

    if metadata.media_type == ImageMediaType.JPEG:
        output_data = _encode_jpeg(normalized, quality=85)
        output_media_type = ImageMediaType.JPEG.value
    else:
        output_data = _encode_png(normalized)
        output_media_type = ImageMediaType.PNG.value
        if len(output_data) > MAX_PNG_OUTPUT_BYTES:
            output_data = _encode_jpeg(normalized, quality=90)
            output_media_type = ImageMediaType.JPEG.value

    return PreparedImage(
        client_image_id=metadata.client_image_id,
        source_file_name=metadata.file_name,
        media_type=output_media_type,
        data=output_data,
        width=normalized.width,
        height=normalized.height,
    )
