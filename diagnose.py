import argparse
import json
from pathlib import Path

import numpy as np
from PIL import ImageEnhance

from features import image_features, open_rgb
from group import similar


def center_crop(image, fraction):
    width, height = image.size
    x = round(width * fraction)
    y = round(height * fraction)
    if min(width - 2 * x, height - 2 * y) < 3:
        raise ValueError("Image is too small for the crop diagnostic")
    return image.crop((x, y, width - x, height - y)).resize(image.size)


def diagnose(path):
    image = open_rgb(path)
    baseline = image_features(image)
    baseline["sha256"] = "original"
    variants = [
        ("center crop 5% per edge", center_crop(image, 0.05)),
        ("center crop 15% per edge", center_crop(image, 0.15)),
        ("exposure 0.7x", ImageEnhance.Brightness(image).enhance(0.7)),
        ("exposure 1.3x", ImageEnhance.Brightness(image).enhance(1.3)),
    ]
    results = []
    for label, changed in variants:
        row = image_features(changed)
        row["sha256"] = label
        results.append({
            "variant": label,
            "matches_original": similar(baseline, row),
            "hash_distance": (int(baseline["dhash"], 16) ^ int(row["dhash"], 16)).bit_count(),
            "pixel_rmse": float(np.sqrt(np.mean((baseline["signature"] - row["signature"]) ** 2))),
            "mean_luma": row["mean_luma"],
        })
    return {"width": image.width, "height": image.height,
            "baseline_luma": baseline["mean_luma"], "variants": results}


def main():
    parser = argparse.ArgumentParser(description="Check grouping sensitivity on one local photo.")
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    try:
        result = diagnose(args.image)
    except (OSError, ValueError) as error:
        parser.exit(2, f"{error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
