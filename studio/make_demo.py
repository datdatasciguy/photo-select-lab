"""Regenerate the two procedural studio preview clips with FFmpeg."""

from pathlib import Path
import shutil
import subprocess


DEMO = Path(__file__).parent / "demo"


def run_ffmpeg(*args):
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise SystemExit("FFmpeg is needed to regenerate the demo clips.")
    subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def main():
    DEMO.mkdir(exist_ok=True)
    source = DEMO / "source.mp4"
    variation = DEMO / "variation.mp4"
    run_ffmpeg(
        "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=24",
        "-t", "4", "-an", "-c:v", "libx264", "-crf", "29",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(source),
    )
    run_ffmpeg(
        "-i", str(source), "-vf", "hue=s=0", "-an", "-c:v", "libx264",
        "-crf", "29", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(variation),
    )
    print(f"Wrote {source.name} and {variation.name} in {DEMO}")


if __name__ == "__main__":
    main()
