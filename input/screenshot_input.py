"""Screenshot validation, normalization, and metadata extraction for WinFix AI.

Strictly validates uploaded image data, enforces dimension and file size ceilings,
computes deterministic SHA-256 hashes, normalizes image buffers to remove metadata,
and ensures no executable files or scripts enter the diagnostic pipeline.
"""

import hashlib
import io
import logging
from typing import List, Optional, Set, Tuple

from PIL import Image, ImageOps

from input.screenshot_models import ScreenshotMetadata

logger = logging.getLogger(__name__)

# Allowed formats
SUPPORTED_IMAGE_FORMATS: Set[str] = {"PNG", "JPEG", "JPG", "WEBP"}

# Size and dimension safety ceilings
MAX_SCREENSHOT_BYTES: int = 10 * 1024 * 1024  # 10 MB
MAX_WIDTH: int = 7680
MAX_HEIGHT: int = 4320
MAX_PIXELS: int = 7680 * 4320  # 33,177,600 pixels


class ScreenshotValidationError(ValueError):
    """Raised when an uploaded screenshot violates format, size, or safety constraints."""

    pass


def validate_and_load_image(
    image_bytes: bytes,
    filename: Optional[str] = None,
) -> Tuple[ScreenshotMetadata, bytes, Image.Image]:
    """Validate, sanitize, normalize, and extract metadata from image bytes.

    Args:
        image_bytes: Raw binary content of the uploaded file.
        filename: Optional filename provided by the client.

    Returns:
        Tuple containing:
            - ScreenshotMetadata: Extracted image metadata and SHA-256 digest.
            - bytes: Sanitized, normalized PNG bytes without embedded metadata.
            - Image.Image: Normalized PIL Image in RGB/RGBA mode.

    Raises:
        ScreenshotValidationError: If file violates any safety, size, or format rule.
    """
    if not image_bytes or not isinstance(image_bytes, bytes):
        raise ScreenshotValidationError("Image data is empty or invalid.")

    file_size = len(image_bytes)
    if file_size > MAX_SCREENSHOT_BYTES:
        raise ScreenshotValidationError(
            f"Image file size ({file_size} bytes) exceeds maximum limit of {MAX_SCREENSHOT_BYTES} bytes (10 MB)."
        )

    # Calculate deterministic SHA-256
    sha256 = hashlib.sha256(image_bytes).hexdigest()
    safe_filename = filename or f"screenshot_{sha256[:12]}.png"

    # Reject forbidden filename extensions before opening
    lower_fn = safe_filename.lower()
    for forbidden_ext in [".svg", ".html", ".htm", ".exe", ".scr", ".bat", ".cmd", ".ps1", ".vbs", ".js"]:
        if lower_fn.endswith(forbidden_ext):
            raise ScreenshotValidationError(
                f"Unsupported or unsafe file extension '{forbidden_ext}'. Supported formats are PNG, JPEG, WEBP."
            )

    try:
        # Load image via Pillow safely
        # Pillow default protects against decompression bombs if MAX_IMAGE_PIXELS is set
        Image.MAX_IMAGE_PIXELS = MAX_PIXELS
        img = Image.open(io.BytesIO(image_bytes))
    except Exception as ex:
        logger.warning("Failed to decode image buffer: %s", ex)
        raise ScreenshotValidationError(f"Invalid image format or corrupted image buffer: {ex}")

    raw_format = (img.format or "").upper()
    if raw_format == "JPG":
        raw_format = "JPEG"

    if raw_format not in SUPPORTED_IMAGE_FORMATS:
        raise ScreenshotValidationError(
            f"Unsupported image format '{raw_format}'. Supported formats: {', '.join(sorted(SUPPORTED_IMAGE_FORMATS))}."
        )

    width, height = img.size
    if width <= 0 or height <= 0:
        raise ScreenshotValidationError(f"Invalid image dimensions ({width}x{height}).")

    if width > MAX_WIDTH or height > MAX_HEIGHT:
        raise ScreenshotValidationError(
            f"Image dimensions ({width}x{height}) exceed maximum allowed dimensions ({MAX_WIDTH}x{MAX_HEIGHT})."
        )

    total_pixels = width * height
    if total_pixels > MAX_PIXELS:
        raise ScreenshotValidationError(
            f"Total image pixel count ({total_pixels}) exceeds safety limit of {MAX_PIXELS} pixels."
        )

    # Normalize orientation if EXIF orientation tag exists
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass

    # Normalize color mode to RGB or RGBA (stripping palettes, CMYK, etc.)
    if img.mode not in ("RGB", "RGBA"):
        if "A" in img.mode or img.mode == "P":
            img = img.convert("RGBA")
        else:
            img = img.convert("RGB")

    width, height = img.size
    aspect_ratio = round(float(width) / float(height), 3) if height > 0 else 1.0

    # Strip metadata and re-encode to clean normalized PNG bytes
    out_buf = io.BytesIO()
    try:
        # Save cleanly as PNG without any source EXIF/metadata
        img.save(out_buf, format="PNG", optimize=True)
        normalized_bytes = out_buf.getvalue()
    finally:
        out_buf.close()

    metadata = ScreenshotMetadata(
        filename=safe_filename,
        format=raw_format,
        width=width,
        height=height,
        file_size=file_size,
        sha256=sha256,
        aspect_ratio=aspect_ratio,
    )

    return metadata, normalized_bytes, img


def inspect_privacy_indicators(filename: Optional[str] = None) -> List[str]:
    """Inspect metadata / filename for obvious sensitive markers and return warnings."""
    warnings: List[str] = []
    if filename:
        fn_lower = filename.lower()
        if any(term in fn_lower for term in ["user", "admin", "pass", "token", "key", "secret", "private", "bank"]):
            warnings.append(f"Filename '{filename}' may reference personal or sensitive account details.")
    warnings.append(
        "Screenshots may display personal paths, email addresses, browser tabs, or account names. Review before analysis."
    )
    return warnings
