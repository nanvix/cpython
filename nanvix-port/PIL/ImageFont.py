"""Lightweight PIL.ImageFont implementation for NanVix.

Provides deterministic text metrics used by python-pptx layout code when
Pillow is unavailable.
"""


class FreeTypeFont:
    def __init__(self, font=None, size=10):
        self.font = font
        self._size = max(1, int(size))

    def _char_width(self, ch):
        # Basic proportional-width estimate:
        # - narrow glyphs
        # - wide glyphs
        # - default glyphs
        if ch in "il.,:;!| ":
            return self._size * 0.35
        if ch in "MW@#%&":
            return self._size * 0.9
        return self._size * 0.6

    def getlength(self, text, *args, **kwargs):
        del args, kwargs
        if text is None:
            return 0.0
        return float(sum(self._char_width(ch) for ch in str(text)))

    def getbbox(self, text, *args, **kwargs):
        del args, kwargs
        width = int(round(self.getlength(text)))
        return (0, 0, width, self._size)


def truetype(font=None, size=10, **kwargs):
    del kwargs
    return FreeTypeFont(font=font, size=size)


def load_default(size=None):
    return FreeTypeFont(size=size or 10)
