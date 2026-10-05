import argparse
import json
from pathlib import Path
import warnings

from PIL import Image

from features import scan_images
from group import group_images, review_order
from report import write_report


def run(folder, output, max_hash_distance=8, max_pixel_rmse=0.08):
    root, output = Path(folder).resolve(), Path(output).resolve()
    if not root.is_dir():
        raise ValueError("Input folder does not exist")
    if output.is_relative_to(root):
        raise ValueError("Keep the report outside the input folder")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Choose an empty output folder to preserve previous reports")
    if not 0 <= max_hash_distance <= 64 or not 0 <= max_pixel_rmse <= 1:
        raise ValueError("Hash distance must be 0..64 and pixel RMSE must be 0..1")
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        records, errors = scan_images(root)
    if not records:
        raise ValueError(f"No readable supported images found ({len(errors)} errors)")
    groups = group_images(records, max_hash_distance, max_pixel_rmse)
    rows = review_order(records, groups)
    write_report(root, output, rows, errors)
    settings = {
        "method": "dhash-rgb-complete-link",
        "max_hash_distance": max_hash_distance, "max_pixel_rmse": max_pixel_rmse,
        "images": len(records), "groups": len(groups), "errors": len(errors),
    }
    (output / "settings.json").write_text(json.dumps(settings, indent=2) + "\n",
                                        encoding="utf-8")
    return settings


def main():
    parser = argparse.ArgumentParser(description="Group similar photos for local review.")
    parser.add_argument("folder", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--hash-distance", type=int, default=8)
    parser.add_argument("--pixel-rmse", type=float, default=0.08)
    args = parser.parse_args()
    try:
        summary = run(args.folder, args.output, args.hash_distance, args.pixel_rmse)
    except (ValueError, OSError) as error:
        parser.exit(1, f"{error}\n")
    print(f'{summary["images"]} images in {summary["groups"]} groups. '
          f'Report: {args.output / "index.html"}')


if __name__ == "__main__":
    main()
