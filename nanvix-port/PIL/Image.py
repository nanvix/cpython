"""Lightweight PIL.Image implementation for NanVix.

This module parses image headers to detect format and dimensions without
decoding pixel data.
"""

from __future__ import annotations

import builtins
import os
import struct

MAX_IMAGE_HEADER_BYTES = 1024 * 1024
MAX_IMAGE_DIMENSION = 100_000
MAX_IMAGE_PIXELS = 100_000_000


def _validate_size(width, height):
    width = int(width)
    height = int(height)
    if width <= 0 or height <= 0:
        raise OSError("image dimensions must be positive")
    if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
        raise OSError("image dimensions exceed supported limit")
    if width * height > MAX_IMAGE_PIXELS:
        raise OSError("image pixel count exceeds supported limit")
    return width, height


class Image:
    def __init__(self, size=(0, 0), fmt=None, mode="RGB", color=None):
        self.size = size
        self.format = fmt
        self.mode = mode
        self.color = color

    @property
    def width(self):
        return self.size[0]

    @property
    def height(self):
        return self.size[1]

    def close(self):
        """Compatibility no-op (no external resources are kept open)."""
        return None


REGISTERED_EXTENSIONS = {}


def register_extension(ext, fmt):
    if not ext:
        raise ValueError("extension must be non-empty")
    if not ext.startswith("."):
        ext = "." + ext
    REGISTERED_EXTENSIONS[ext.lower()] = fmt


def _read_all_bytes(fp):
    if hasattr(fp, "read"):
        # Preserve caller stream position when possible.
        pos = None
        can_seek = hasattr(fp, "seek") and hasattr(fp, "tell")
        if can_seek:
            try:
                pos = fp.tell()
            except Exception:
                pos = None
        data = fp.read(MAX_IMAGE_HEADER_BYTES + 1)
        if pos is not None:
            try:
                fp.seek(pos)
            except Exception:
                pass
    else:
        with builtins.open(os.fspath(fp), "rb") as fobj:
            data = fobj.read(MAX_IMAGE_HEADER_BYTES + 1)

    if not isinstance(data, (bytes, bytearray)):
        raise OSError("image stream must return bytes")
    if len(data) > MAX_IMAGE_HEADER_BYTES:
        raise OSError("image header exceeds supported limit")
    return bytes(data)


def _parse_png(data):
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    if len(data) < 26:
        raise OSError("truncated PNG header")
    if data[12:16] != b"IHDR":
        raise OSError("invalid PNG: missing IHDR")
    width, height = struct.unpack(">II", data[16:24])
    width, height = _validate_size(width, height)
    color_type = data[25]
    mode_map = {0: "L", 2: "RGB", 3: "P", 4: "LA", 6: "RGBA"}
    return Image(size=(width, height), fmt="PNG", mode=mode_map.get(color_type, "RGB"))


def _parse_gif(data):
    if not (data.startswith(b"GIF87a") or data.startswith(b"GIF89a")):
        return None
    if len(data) < 10:
        raise OSError("truncated GIF header")
    width, height = struct.unpack("<HH", data[6:10])
    width, height = _validate_size(width, height)
    return Image(size=(width, height), fmt="GIF", mode="P")


def _parse_bmp(data):
    if not data.startswith(b"BM"):
        return None
    if len(data) < 30:
        raise OSError("truncated BMP header")
    dib_header_size = struct.unpack("<I", data[14:18])[0]
    if dib_header_size < 40:
        raise OSError("unsupported BMP header")
    width = abs(struct.unpack("<i", data[18:22])[0])
    height = abs(struct.unpack("<i", data[22:26])[0])
    width, height = _validate_size(width, height)
    bpp = struct.unpack("<H", data[28:30])[0]
    mode = "RGBA" if bpp == 32 else ("RGB" if bpp >= 24 else "P")
    return Image(size=(width, height), fmt="BMP", mode=mode)


def _parse_jpeg(data):
    if not data.startswith(b"\xff\xd8"):
        return None
    i = 2
    sof_markers = {
        0xC0,
        0xC1,
        0xC2,
        0xC3,
        0xC5,
        0xC6,
        0xC7,
        0xC9,
        0xCA,
        0xCB,
        0xCD,
        0xCE,
        0xCF,
    }
    while i + 1 < len(data):
        while i < len(data) and data[i] != 0xFF:
            i += 1
        if i + 1 >= len(data):
            break
        while i < len(data) and data[i] == 0xFF:
            i += 1
        if i >= len(data):
            break

        marker = data[i]
        i += 1

        # Standalone markers (no segment length).
        if marker in {0x01, 0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue

        if i + 1 >= len(data):
            raise OSError("truncated JPEG segment")
        seglen = struct.unpack(">H", data[i : i + 2])[0]
        if seglen < 2:
            raise OSError("invalid JPEG segment length")
        if i + seglen > len(data):
            raise OSError("truncated JPEG segment payload")

        if marker in sof_markers:
            if seglen < 8:
                raise OSError("invalid JPEG SOF segment")
            height, width = struct.unpack(">HH", data[i + 3 : i + 7])
            width, height = _validate_size(width, height)
            components = data[i + 7]
            mode = {1: "L", 3: "RGB", 4: "CMYK"}.get(components, "RGB")
            return Image(size=(width, height), fmt="JPEG", mode=mode)

        i += seglen

    raise OSError("could not find JPEG SOF marker")


def _read_tiff_value(data, endian, entry_type, count, raw_value):
    # TIFF field types used for basic dimensions.
    type_sizes = {1: 1, 3: 2, 4: 4}
    unit = type_sizes.get(entry_type)
    if unit is None:
        return None
    total_size = unit * count

    if total_size <= 4:
        if entry_type == 3:  # SHORT
            return struct.unpack(endian + "H", raw_value[:2])[0]
        if entry_type == 4:  # LONG
            return struct.unpack(endian + "I", raw_value)[0]
        return raw_value[0]

    value_offset = struct.unpack(endian + "I", raw_value)[0]
    if value_offset + total_size > len(data):
        return None
    blob = data[value_offset : value_offset + total_size]
    if entry_type == 3:
        return struct.unpack(endian + "H", blob[:2])[0]
    if entry_type == 4:
        return struct.unpack(endian + "I", blob[:4])[0]
    return blob[0]


def _parse_tiff(data):
    if len(data) < 8:
        return None
    if data[:2] == b"II":
        endian = "<"
    elif data[:2] == b"MM":
        endian = ">"
    else:
        return None

    magic = struct.unpack(endian + "H", data[2:4])[0]
    if magic != 42:
        raise OSError("unsupported TIFF variant")

    ifd_offset = struct.unpack(endian + "I", data[4:8])[0]
    if ifd_offset + 2 > len(data):
        raise OSError("truncated TIFF IFD offset")

    entry_count = struct.unpack(endian + "H", data[ifd_offset : ifd_offset + 2])[0]
    cursor = ifd_offset + 2
    width = None
    height = None
    mode = "RGB"

    for _ in range(entry_count):
        if cursor + 12 > len(data):
            raise OSError("truncated TIFF IFD entry")
        tag, entry_type, count = struct.unpack(endian + "HHI", data[cursor : cursor + 8])
        raw_value = data[cursor + 8 : cursor + 12]
        value = _read_tiff_value(data, endian, entry_type, count, raw_value)
        if tag == 256 and value is not None:  # ImageWidth
            width = int(value)
        elif tag == 257 and value is not None:  # ImageLength
            height = int(value)
        elif tag == 262 and value in (0, 1):  # PhotometricInterpretation
            mode = "L"
        cursor += 12

        if width is not None and height is not None:
            width, height = _validate_size(width, height)
            return Image(size=(width, height), fmt="TIFF", mode=mode)

    raise OSError("TIFF width/height tags not found")


def open(fp, mode="r", formats=None):
    """Open image metadata from *fp* without decoding pixels."""
    if mode not in {"r", "rb"}:
        raise ValueError("only read mode is supported")

    data = _read_all_bytes(fp)
    if len(data) < 2:
        raise OSError("truncated image file")

    parsers = (_parse_png, _parse_jpeg, _parse_gif, _parse_bmp, _parse_tiff)
    image = None
    errors = []
    for parser in parsers:
        try:
            image = parser(data)
        except OSError as exc:
            errors.append(str(exc))
            break
        if image is not None:
            break

    if image is None:
        if errors:
            raise OSError(errors[0])
        raise OSError("cannot identify image file")

    if formats is not None:
        normalized = {f.upper() for f in formats}
        if image.format not in normalized:
            raise OSError(f"image format {image.format} not in allowed formats")
    return image


def new(mode, size, color=0):
    if not (isinstance(size, tuple) and len(size) == 2):
        raise ValueError("size must be a (width, height) tuple")
    try:
        width, height = _validate_size(size[0], size[1])
    except OSError as exc:
        raise ValueError(str(exc)) from exc
    return Image(size=(width, height), fmt=None, mode=mode, color=color)
