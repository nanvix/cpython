"""Minimal PIL.ImageOps compatibility for NanVix."""


def exif_transpose(image, *, in_place=False):
    if in_place:
        return None
    return image
