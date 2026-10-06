import argparse
import json
import os
import platform
import random
import statistics
import tempfile
import time
from pathlib import Path

import numpy
from PIL import Image, ImageDraw, ImageFilter, __version__ as pillow_version

from features import scan_images
from group import group_images

def make_scene(number):
    rng = random.Random(20261006 + number)
    image = Image.new("RGB", (640, 420), tuple(rng.randrange(40, 220) for _ in range(3)))
    draw = ImageDraw.Draw(image)
    for _ in range(12):
        x, y = rng.randrange(600), rng.randrange(380)
        color = tuple(rng.randrange(20, 240) for _ in range(3))
        draw.rectangle((x, y, x + 40, y + 40), fill=color)
    return image

def make_batch(folder, count):
    folder.mkdir()
    for index in range(count):
        scene = make_scene(index // 4)
        variant = index % 4
        if variant == 2:
            scene.save(folder / f"image_{index:04d}.jpg", quality=90)
        elif variant == 3:
            scene.filter(ImageFilter.GaussianBlur(1.5)).save(folder / f"image_{index:04d}.png")
        else:
            scene.save(folder / f"image_{index:04d}.png")

def benchmark(folder, count, repeats):
    make_batch(folder, count)
    scan_times = []
    group_times = []
    for _ in range(repeats):
        start = time.perf_counter()
        records, errors = scan_images(folder)
        scan_times.append(time.perf_counter() - start)
        if errors or len(records) != count:
            raise RuntimeError("Generated batch did not scan cleanly")
        start = time.perf_counter()
        groups = group_images(records)
        group_times.append(time.perf_counter() - start)
    return {
        "images": count,
        "groups": len(groups),
        "errors": len(errors),
        "scan_seconds": round(statistics.median(scan_times), 6),
        "group_seconds": round(statistics.median(group_times), 6),
    }

def main():
    # Arguments
    parser = argparse.ArgumentParser(description="Time photo scanning and grouping on generated images.")
    parser.add_argument("--sizes", nargs="+", type=int, default=[40, 80, 160, 320])
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if any(size < 1 for size in args.sizes) or args.repeats < 1:
        parser.error("Sizes and repeats must be positive")
    if len(set(args.sizes)) != len(args.sizes):
        parser.error("Sizes must be unique")
    info = {
        "system": platform.platform(),
        "processor": platform.processor(),
        "logical_cpus": os.cpu_count(),
        "python": platform.python_version(),
        "numpy": numpy.__version__,
        "pillow": pillow_version,
        "repeats": args.repeats,
        "results": [],
    }
    with tempfile.TemporaryDirectory(prefix="photo-select-benchmark-") as temporary:
        for size in args.sizes:
            info["results"].append(benchmark(Path(temporary) / str(size), size, args.repeats))
    print(json.dumps(info, indent=2))

if __name__ == "__main__":
    main()
