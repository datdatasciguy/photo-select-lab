import csv
from collections import defaultdict
from html import escape
from pathlib import Path

from features import open_rgb

def write_csv(path, rows, fields):
    with Path(path).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

def write_thumbnail(source, destination):
    image = open_rgb(source)
    image.thumbnail((480, 320))
    # Remove metadata from the preview
    image.info.clear()
    image.save(destination, quality=85)

def image_card(row, thumbnail):
    filename = escape(row["file"], quote=True)
    return (
        f'<article><img loading="lazy" src="thumbnails/{thumbnail}" alt="{filename}">'
        f'<div class="caption"><b>{filename}</b>'
        f'<p>Review order {row["rank"]} &middot; {row["width"]} × {row["height"]}</p>'
        f'<p>Sharpness {row["sharpness"]:.5f} &middot; dark {row["dark_fraction"]:.1%}'
        f' &middot; bright {row["bright_fraction"]:.1%}</p></div></article>'
    )

def render_page(grouped, image_count, error_count):
    sections = []
    for number, cards in grouped.items():
        sections.append(f'<section><h2>Group {number} <small>{len(cards)} image(s)</small>'
                        '</h2><div class="grid">' + "".join(cards) + '</div></section>')
    error_note = (f'<p>{error_count} file(s) could not be analyzed. See errors.csv.</p>'
                  if error_count else "")
    page = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Photo review</title><style>
body{font:15px/1.5 system-ui,sans-serif;margin:0;background:#f3f1ec;color:#24313a}
main{max-width:1180px;margin:auto;padding:36px 24px}h1{font-size:32px;margin-bottom:8px}
small{font-size:14px;color:#67727a;font-weight:400;margin-left:10px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:18px}
article{background:white;border:1px solid #ddd;border-radius:6px;overflow:hidden}
img{width:100%;height:210px;object-fit:contain;background:#e9e7e2}
.caption{padding:14px;overflow-wrap:anywhere}.caption p{margin:6px 0;color:#53606a}
section{margin:30px 0}.intro{max-width:800px}
</style></head><body><main><h1>Photo review</h1>
<p class="intro">Similar images, grouped for comparison. Review order uses a sharpness
baseline, not a learned preference or an artistic-quality score. No originals are changed.</p>"""
    page += f'<p>{image_count} images · {len(grouped)} groups</p>' + error_note
    page += "".join(sections) + "</main></body></html>"
    return page

def write_report(folder, output, rows, errors):
    root = Path(folder)
    output = Path(output)
    thumbs = output / "thumbnails"
    thumbs.mkdir(parents=True, exist_ok=True)

    # Save image stats and skipped files
    fields = ["group", "rank", "file", "width", "height", "sharpness", "mean_luma",
              "dark_fraction", "bright_fraction", "sha256", "dhash"]
    write_csv(output / "manifest.csv", rows, fields)
    write_csv(output / "errors.csv", errors, ["file", "error"])

    # Create one preview per unique file
    grouped = defaultdict(list)
    written = set()
    for row in rows:
        thumbnail = row["sha256"] + ".jpg"
        if thumbnail not in written:
            write_thumbnail(root / row["file"], thumbs / thumbnail)
            written.add(thumbnail)
        grouped[row["group"]].append(image_card(row, thumbnail))

    page = render_page(grouped, len(rows), len(errors))
    (output / "index.html").write_text(page, encoding="utf-8")
