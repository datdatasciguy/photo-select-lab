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
    digest = escape(row["sha256"], quote=True)
    return (
        f'<article class="review-card" data-file="{filename}" data-sha256="{digest}" '
        f'data-group="{row["group"]}" data-rank="{row["rank"]}">'
        f'<img loading="lazy" src="thumbnails/{thumbnail}" alt="{filename}">'
        f'<div class="caption"><b>{filename}</b>'
        f'<p>Review order {row["rank"]} &middot; {row["width"]} × {row["height"]}</p>'
        f'<p>Sharpness {row["sharpness"]:.5f} &middot; dark {row["dark_fraction"]:.1%}'
        f' &middot; bright {row["bright_fraction"]:.1%}</p>'
        '<div class="choices" aria-label="Review choice">'
        '<button type="button" data-choice="keep" aria-pressed="false">Keep</button>'
        '<button type="button" data-choice="reject" aria-pressed="false">Reject</button>'
        '<button type="button" data-choice="unsure" aria-pressed="false">Unsure</button>'
        '</div></div></article>'
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
.toolbar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:18px 0}
.toolbar button,.file-button,.choices button{font:inherit;padding:6px 10px;border:1px solid #89969d;border-radius:5px;background:white;cursor:pointer}
.file-button input{display:none}.choices{display:flex;gap:6px;flex-wrap:wrap}
.choices button[aria-pressed="true"]{background:#234e61;color:white;border-color:#234e61}
</style></head><body><main><h1>Photo review</h1>
<p class="intro">Similar images, grouped for comparison. Review order uses a sharpness
baseline, not a learned preference or an artistic-quality score. No originals are changed.
Choose Keep, Reject, or Unsure, then save labels before closing this page. The
JSON stays on your computer; load it here to continue reviewing later.</p>
<div class="toolbar"><button type="button" id="save-labels">Save labels JSON</button>
<label class="file-button">Load labels JSON<input id="load-labels" type="file" accept=".json,application/json"></label>
<span id="review-status" role="status" aria-live="polite">No labels yet</span></div>"""
    page += f'<p>{image_count} images · {len(grouped)} groups</p>' + error_note
    page += "".join(sections) + """</main><script>
const cards = [...document.querySelectorAll('.review-card')];
const status = document.querySelector('#review-status');
const choices = new Set(['keep', 'reject', 'unsure']);

function setChoice(card, choice, reviewedAt) {
  card.dataset.choice = choice;
  card.dataset.reviewedAt = reviewedAt;
  for (const button of card.querySelectorAll('[data-choice]')) {
    button.setAttribute('aria-pressed', String(button.dataset.choice === choice));
  }
  status.textContent = `${cards.filter(item => item.dataset.choice).length} of ${cards.length} labeled`;
}

document.addEventListener('click', event => {
  const button = event.target.closest('.choices button');
  if (button) setChoice(button.closest('.review-card'), button.dataset.choice, new Date().toISOString());
});

document.querySelector('#save-labels').addEventListener('click', () => {
  const rows = cards.map(card => ({
    file: card.dataset.file,
    sha256: card.dataset.sha256,
    group: Number(card.dataset.group),
    rank: Number(card.dataset.rank),
    label: card.dataset.choice || '',
    reviewed_at: card.dataset.reviewedAt || ''
  }));
  const payload = {schema_version: 1, exported_at: new Date().toISOString(), rows};
  const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2) + '\\n'], {type: 'application/json'}));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'photo-review-labels.json';
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});

document.querySelector('#load-labels').addEventListener('change', async event => {
  const file = event.target.files[0];
  if (!file) return;
  try {
    const payload = JSON.parse(await file.text());
    if (payload.schema_version !== 1 || !Array.isArray(payload.rows)) throw new Error('Unsupported label file');
    const current = new Map(cards.map(card => [card.dataset.file + ':' + card.dataset.sha256, card]));
    const seen = new Set();
    for (const row of payload.rows) {
      const key = row.file + ':' + row.sha256;
      if (!current.has(key) || seen.has(key) || typeof row.label !== 'string' ||
          (row.label !== '' && !choices.has(row.label)) ||
          typeof row.reviewed_at !== 'string') throw new Error('Labels do not match this report');
      seen.add(key);
    }
    if (seen.size !== cards.length) throw new Error('Labels do not match this report');
    for (const row of payload.rows) {
      setChoice(current.get(row.file + ':' + row.sha256), row.label, row.reviewed_at);
    }
    status.textContent += ' (loaded)';
  } catch (error) {
    status.textContent = error.message;
  }
  event.target.value = '';
});
</script></body></html>"""
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
