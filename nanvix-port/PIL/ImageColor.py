"""Minimal PIL.ImageColor compatibility for NanVix."""

_NAMED = {
    "black": (0, 0, 0),
    "white": (255, 255, 255),
    "red": (255, 0, 0),
    "green": (0, 128, 0),
    "blue": (0, 0, 255),
    "yellow": (255, 255, 0),
    "cyan": (0, 255, 255),
    "magenta": (255, 0, 255),
    "transparent": (0, 0, 0, 0),
}


def getrgb(color):
    if isinstance(color, tuple):
        return color
    if not isinstance(color, str):
        raise ValueError("unknown color specifier")
    value = color.strip().lower()
    if value in _NAMED:
        return _NAMED[value]
    if value.startswith("#") and len(value) in (4, 7):
        if len(value) == 4:
            return tuple(int(ch * 2, 16) for ch in value[1:])
        return tuple(int(value[i : i + 2], 16) for i in (1, 3, 5))
    raise ValueError(f"unknown color specifier: {color!r}")
