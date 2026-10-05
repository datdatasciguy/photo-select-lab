from pathlib import Path
import argparse

from PIL import Image, ImageDraw, ImageFilter


def create_demo(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("Choose an empty demo folder")
    scene = Image.new("RGB", (640, 420), "#c4d8e5")
    draw = ImageDraw.Draw(scene)
    draw.rectangle((0, 235, 640, 420), fill="#477c68")
    draw.ellipse((425, 45, 495, 115), fill="#f2d497")
    draw.rectangle((140, 130, 315, 340), fill="#ede7d8")
    for x in range(150, 310, 18):
        draw.line((x, 140, x, 330), fill="#576870", width=3)
    draw.polygon([(335, 310), (395, 165), (475, 310)], fill="#b97758")
    scene.save(output / "scene.png")
    scene.save(output / "scene_copy.png")
    scene.save(output / "scene_jpeg.jpg", quality=90)
    scene.filter(ImageFilter.GaussianBlur(3)).save(output / "scene_soft.png")
    other = Image.new("RGB", (640, 420), "#202944")
    draw = ImageDraw.Draw(other)
    for x in range(25, 640, 65):
        draw.ellipse((x, 80, x + 35, 250), fill="#b79ba8")
    other.save(output / "different_scene.png")
    Image.new("RGB", (640, 420), "#d32b32").save(output / "red.png")
    Image.new("RGB", (640, 420), "#2965d1").save(output / "blue.png")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create original procedural diagnostic images.")
    parser.add_argument("output", type=Path)
    create_demo(parser.parse_args().output)
