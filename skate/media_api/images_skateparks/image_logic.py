from io import BytesIO

from PIL import Image, ImageOps


def image_resize_800(file):
    """Keep uploaded spot photos sharp while still reducing file size.

    The old implementation always squeezed each image down to 800px on its
    longest side, which made otherwise high-quality photos look soft. We keep
    the same “normalise uploaded files” workflow, but cap the long side at 1600px
    and use a much lighter JPEG/WebP compression profile.
    """

    image = Image.open(file)
    image = ImageOps.exif_transpose(image)

    if image.mode in {"RGBA", "LA", "P"}:
        image = image.convert("RGB")

    image.thumbnail((1600, 1600), getattr(Image, "Resampling", Image).LANCZOS)

    output = BytesIO()
    save_format = image.format or "JPEG"
    save_args = {"format": save_format, "quality": 92, "optimize": True}

    if save_format in {"JPEG", "WEBP"}:
        save_args["subsampling"] = 0

    image.save(output, **save_args)
    output.seek(0)
    return output