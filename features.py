from hashlib import sha256
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}

def open_rgb(path):
    with Image.open(path) as image:
        if getattr(image, "n_frames", 1) > 1:
            raise ValueError("Animated or multi-page images are not supported")
        image = ImageOps.exif_transpose(image)
        if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
            background = Image.new("RGBA", image.size, "white")
            image = Image.alpha_composite(background, image.convert("RGBA"))
        return image.convert("RGB")

def difference_hash(image):
    gray = np.asarray(image.convert("L").resize((9, 8), Image.Resampling.LANCZOS))
    # Compare neighboring pixels to build the hash
    bits = (gray[:, 1:] > gray[:, :-1]).ravel()
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return f"{value:016x}"

def image_features(image):
    width, height = image.size
    if min(width, height) < 3:
        raise ValueError("Image must be at least 3 pixels in each dimension")
    # Measure sharpness at a common maximum size
    preview = image.copy()
    preview.thumbnail((768, 768), Image.Resampling.LANCZOS)
    gray = np.asarray(preview.convert("L"), dtype=np.float64) / 255
    center = gray[1:-1, 1:-1]
    if min(gray.shape) < 3:
        raise ValueError("Aspect ratio is too extreme for a comparable sharpness measurement")
    laplacian = (gray[:-2, 1:-1] + gray[2:, 1:-1]
                 + gray[1:-1, :-2] + gray[1:-1, 2:] - 4 * center)
    small = np.asarray(image.resize((16, 16), Image.Resampling.BILINEAR),
                       dtype=np.float64) / 255
    return {
        "width": width,
        "height": height,
        "aspect": width / height,
        "sharpness": float(laplacian.var()),
        "mean_luma": float(gray.mean()),
        "dark_fraction": float((gray <= 5 / 255).mean()),
        "bright_fraction": float((gray >= 250 / 255).mean()),
        "dhash": difference_hash(image),
        "signature": small.ravel(),
    }

def file_digest(path):
    digest = sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def scan_images(folder):
    root = Path(folder).resolve()
    records = []
    errors = []
    paths = sorted(p for p in root.rglob("*")
                   if p.is_file() and p.suffix.lower() in EXTENSIONS)
    for path in paths:
        relative = path.relative_to(root).as_posix()
        if not path.resolve().is_relative_to(root):
            errors.append({"file": relative, "error": "Link points outside input folder"})
            continue
        try:
            image = open_rgb(path)
            row = image_features(image)
            row.update(file=relative, sha256=file_digest(path))
            records.append(row)
        except (OSError, ValueError, Image.DecompressionBombError,
                Image.DecompressionBombWarning) as error:
            errors.append({"file": relative, "error": type(error).__name__})
    return records, errors
