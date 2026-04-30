"""Smoke tests for NanVix PPTX support."""

import io
import sys
import unittest
import zipfile
from pathlib import Path

_repo_pil = Path(__file__).resolve().parents[2] / "nanvix-port"
if _repo_pil.is_dir():
    sys.path.insert(0, str(_repo_pil))

from PIL import Image, ImageColor, ImageFont, ImageOps


class NanvixPptxTests(unittest.TestCase):
    def test_pil_png_metadata(self):
        data = (
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR"
            + (32).to_bytes(4, "big")
            + (16).to_bytes(4, "big")
            + b"\x08\x02\x00\x00\x00"
        )
        image = Image.open(io.BytesIO(data))
        self.assertEqual(image.size, (32, 16))
        self.assertEqual(image.mode, "RGB")

    def test_pil_rejects_huge_dimensions(self):
        data = (
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR"
            + (2**32 - 1).to_bytes(4, "big")
            + (2**32 - 1).to_bytes(4, "big")
            + b"\x08\x02\x00\x00\x00"
        )
        with self.assertRaises(OSError):
            Image.open(io.BytesIO(data))

    def test_pil_compat_modules(self):
        self.assertEqual(ImageColor.getrgb("#0f0"), (0, 255, 0))
        image = Image.new("RGB", (10, 20), "red")
        self.assertIs(ImageOps.exif_transpose(image), image)
        self.assertGreater(ImageFont.truetype("missing.ttf", 12).getlength("abc"), 0)

    def test_python_pptx(self):
        from pptx import Presentation

        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[0])
        slide.shapes.title.text = "NanVix PPTX"
        buf = io.BytesIO()
        prs.save(buf)
        self.assertGreater(len(buf.getvalue()), 1000)
        self.assertTrue(zipfile.is_zipfile(io.BytesIO(buf.getvalue())))


if __name__ == "__main__":
    unittest.main()
