"""Minimal PIL.ImageFont stub for python-pptx text layout."""


class FreeTypeFont:
    def __init__(self, font=None, size=10):
        self._size = size

    def getlength(self, text, *args, **kwargs):
        return len(text) * self._size * 0.6

    def getbbox(self, text, *args, **kwargs):
        w = len(text) * self._size * 0.6
        return (0, 0, int(w), self._size)


def truetype(font=None, size=10, **kwargs):
    return FreeTypeFont(font, size)


def load_default(size=None):
    return FreeTypeFont(size=size or 10)
