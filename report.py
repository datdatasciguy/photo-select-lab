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


def write_report(folder, output, rows, errors):
    root, output = Path(folder), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    thumbs = output / "thumbnails"
    thumbs.mkdir(exist_ok=True)
    fields = ["group", "rank", "file", "width", "height", "sharpness", "mean_luma",
              "dark_fraction", "bright_fraction", "sha256", "dhash"]
    write_csv(output / "manifest.csv", rows, fields)
    write_csv(output / "errors.csv", errors, ["file", "error"])
    grouped = defaultdict(list)
    for row in rows:
        image = open_rgb(root / row["file"])
        image.thumbnail((480, 320))
        thumb = row["sha256"] + ".jpg"
        # A new RGB image drops input metadata from the portable preview.
        clean = image.copy()
        clean.info.clear()
        clean.save(thumbs / thumb, quality=85)
        grouped[row["group"]].append(
            '<article><img loading="lazy" src="thumbnails/' + thumb + '" alt="'
            + escape(row["file"], quote=True) + '"><div class="caption"><b>'
            + escape(row["file"]) + '</b><p>Review order '
            + str(row["rank"]) + ' &middot; ' + str(row["width"]) + ' × '
            + str(row["height"]) + '</p><p>Sharpness '
            + f'{row["sharpness"]:.5f}' + ' &middot; dark '
            + f'{row["dark_fraction"]:.1%}' + ' &middot; bright '
            + f'{row["bright_fraction"]:.1%}' + '</p></div></article>'
        )
    sections = []
    for number, cards in grouped.items():
        sections.append(f'<section><h2>Group {number} <small>{len(cards)} image(s)</small>'
                        '</h2><div class="grid">' + "".join(cards) + '</div></section>')
    error_note = (f'<p>{len(errors)} file(s) could not be analyzed. See errors.csv.</p>'
                  if errors else "")
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
    page += f'<p>{len(rows)} images · {len(grouped)} groups</p>' + error_note
    page += "".join(sections) + "</main></body></html>"
    (output / "index.html").write_text(page, encoding="utf-8")
