"""Minimal PIL.Image stub — enough for python-pptx to import and do basic ops."""


class Image:
    def __init__(self):
        self.size = (0, 0)
        self.format = None
        self.mode = "RGB"

    @property
    def width(self):
        return self.size[0]

    @property
    def height(self):
        return self.size[1]

    def close(self):
        pass


def open(fp, mode="r", formats=None):
    """Stub — returns a dummy image with basic header-based size detection."""
    img = Image()
    import struct
    if hasattr(fp, "read"):
        data = fp.read(32)
        fp.seek(0)
    else:
        data = b""
    # PNG size detection
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        w, h = struct.unpack(">II", data[16:24])
        img.size = (w, h)
        img.format = "PNG"
    elif data[:2] == b"\xff\xd8":
        img.format = "JPEG"
    return img


def new(mode, size, color=0):
    img = Image()
    img.mode = mode
    img.size = size
    return img


REGISTERED_EXTENSIONS = {}


def register_extension(ext, fmt):
    REGISTERED_EXTENSIONS[ext] = fmt
