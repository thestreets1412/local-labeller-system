from array import array

import pytest

from visionlabel import texture


def test_all_channels_match_previous_conversion_exactly(monkeypatch):
    pixels = bytes(range(256)) * 4
    expected = array("f", (value / 255 for value in pixels)).tobytes()
    assert texture.rgba_texture(pixels).tobytes() == expected
    monkeypatch.setattr(texture, "_native_convert", None)
    assert texture.rgba_texture(pixels).tobytes() == expected


def test_native_wheel_matches_fallback():
    native = pytest.importorskip("visionlabel_native")
    pixels = bytes(range(256)) * 1024
    assert native.rgba_to_float(pixels) == array("f", (v / 255 for v in pixels)).tobytes()
    assert native.rgba_to_float(b"") == b""
    with pytest.raises(ValueError):
        native.rgba_to_float(b"abc")


@pytest.mark.parametrize("pixels", [b"x", bytes(2048 * 2048 * 4 + 4)], ids=["unaligned", "too-large"])
def test_invalid_texture_is_rejected(pixels):
    with pytest.raises(ValueError):
        texture.rgba_texture(pixels)
