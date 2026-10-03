"""Read dimensions encoded in official image filenames without network access."""

import re
from urllib.parse import unquote, urlsplit


_IMAGE_PATH = re.compile(
    r"/ling-gtq/guixiuxian_imgs/raw/master/(?:items|titles)/"
    r"[^/\\]+__([0-9]+)x([0-9]+)\."
    r"(?i:png|jpe?g|gif|webp|bmp|dib|tiff?|ico|icns|ppm|pgm|pbm|pnm|"
    r"pcx|tga|dds|eps|ps|pdf|avif|apng|jp2|j2k|jpf|jpx|jpc|jxr|"
    r"psd|sgi|rgb|rgba|bw|im|msp|xbm|xpm|qoi)$",
)
_HOSTS = {"raw.giteeusercontent.com", "gitee.com"}


def parse_image_dimensions(image_url: str) -> tuple[int, int] | None:
    """Accept only HTTPS raw/master images in our repository with positive sizes."""
    if any(ord(char) < 32 or ord(char) == 127 for char in image_url):
        return None
    try:
        url = urlsplit(image_url)
        if (
            url.scheme != "https"
            or url.netloc.lower() not in _HOSTS
            or url.username is not None
            or url.password is not None
        ):
            return None
        path = unquote(url.path)
        match = _IMAGE_PATH.fullmatch(path)
        if not match:
            return None
        width, height = map(int, match.groups())
    except ValueError:
        return None
    return (width, height) if width > 0 and height > 0 else None


def scale_image_dimensions(
    width: int, height: int, max_width: int, max_height: int | None = None,
) -> tuple[int, int]:
    """Fit within the supplied limits without enlargement, retaining at least one pixel."""
    if width <= 0 or height <= 0 or max_width <= 0 or (max_height is not None and max_height <= 0):
        raise ValueError("Image dimensions and limits must be positive")
    numerator, denominator = min(width, max_width), width
    if max_height is not None and max_height * denominator < height * numerator:
        numerator, denominator = max_height, height
    return max(1, width * numerator // denominator), max(1, height * numerator // denominator)
