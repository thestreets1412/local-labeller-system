"""Optional native conversion; keep the dependency-free implementation usable."""

from array import array

try:
    from visionlabel_native import rgba_to_float as _native_convert
except ImportError:
    _native_convert = None


def rgba_texture(pixels: bytes) -> array:
    if len(pixels) % 4 or len(pixels) > 2048 * 2048 * 4:
        raise ValueError("Expected RGBA bytes up to 2048 x 2048 pixels.")
    if _native_convert is None:
        return array("f", (component / 255 for component in pixels))
    result = array("f")
    result.frombytes(_native_convert(pixels))
    return result
