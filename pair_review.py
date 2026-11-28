import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict
from html import escape
from pathlib import Path
from random import Random

def make_pairs(report, max_opponents, orientation_seed=None):
    with (report / "manifest.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    groups = defaultdict(list)
    for row in rows:
        digest = row["sha256"]
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Invalid thumbnail digest in manifest")
        if not (report / "thumbnails" / f"{digest}.jpg").is_file():
            raise ValueError("A report thumbnail is missing")
        groups[int(row["group"])].append(row)
    pairs = []
    for group, members in sorted(groups.items()):
        unique = {}
        for row in sorted(members, key=lambda item: int(item["rank"])):
            unique.setdefault(row["sha256"], row)
        candidates = list(unique.values())
        for other in candidates[1:max_opponents + 1]:
            left = candidates[0]
            key = f"{group}:{left['sha256']}:{other['sha256']}"
            pairs.append({"id": hashlib.sha256(key.encode()).hexdigest()[:20],
                          "group": group, "left": left, "right": other})
    if not pairs:
        raise ValueError("No groups have two distinct images to compare")
    if orientation_seed is not None:
        rng = Random(orientation_seed)
        for pair in pairs:
            if rng.random() < 0.5:
                pair["left"], pair["right"] = pair["right"], pair["left"]
        rng.shuffle(pairs)
    return pairs

def render_page(pairs, orientation_seed=None):
    cards = []
    for pair in pairs:
        sides = []
        for role in ("left", "right"):
            row = pair[role]
            name = escape(row["file"])
            digest = row["sha256"]
            sides.append(f'<figure><img src="thumbnails/{digest}.jpg" alt="{name}">'
                         f'<figcaption>{name}</figcaption></figure>')
        cards.append(f'<article class="pair" data-id="{pair["id"]}" '
                     f'data-left="{pair["left"]["sha256"]}" data-right="{pair["right"]["sha256"]}" '
                     f'data-group="{pair["group"]}"><h2>Group {pair["group"]}</h2>'
                     f'<div class="images">{"".join(sides)}</div><div class="choices" role="group" '
                     f'aria-label="Choose preferred image"><button data-choice="left">Left</button>'
                     f'<button data-choice="right">Right</button><button data-choice="tie">Tie</button>'
                     f'<button data-choice="unsure">Unsure</button></div></article>')
    intro = ("Pair order and left/right placement are shuffled with a saved seed. "
             "The first image is not always the baseline leader." if orientation_seed is not None else
             "The first image is the existing review order's leader.")
    return """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Photo pair review</title><style>
body{font:16px/1.5 system-ui,sans-serif;max-width:1120px;margin:auto;padding:24px;background:#f3f5f5;color:#1c2c33}
p{max-width:75ch}.toolbar{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:20px 0}
article{background:white;border:1px solid #d3dddf;border-radius:9px;padding:16px;margin:20px 0}
h2{font-size:17px;margin:0 0 12px}.images{display:grid;grid-template-columns:1fr 1fr;gap:12px}
figure{margin:0;min-width:0}img{width:100%;height:300px;object-fit:contain;background:#e6ebed}
figcaption{overflow-wrap:anywhere;font-size:13px}.choices{display:flex;gap:8px;margin-top:15px;flex-wrap:wrap}
button,.load{font:inherit;border:1px solid #69818c;border-radius:6px;padding:7px 12px;background:white;cursor:pointer}
button[aria-pressed=true]{background:#195e70;color:white}.load input{display:none}
@media(max-width:650px){.images{grid-template-columns:1fr}img{height:230px}}
</style><h1>Photo pair review</h1>
<p>Pick the image you prefer in each pair, or choose Tie or Unsure. The pairs come from the same report group. """ + intro + """ These are direct choices, separate from Keep/Reject labels. Files stay on your computer.</p>
<div class="toolbar"><button id="save" type="button">Save votes JSON</button>
<label class="load">Load votes JSON<input id="load" type="file" accept=".json,application/json"></label>
<span id="status" role="status" aria-live="polite">No votes yet</span></div>
""" + "".join(cards) + "<script>\nconst orientationSeed = " + json.dumps(orientation_seed) + ";\n" + """
const cards = [...document.querySelectorAll('.pair')];
const status = document.querySelector('#status');
const choices = new Set(['left', 'right', 'tie', 'unsure']);
function setChoice(card, choice, reviewedAt) {
  card.dataset.choice = choice;
  card.dataset.reviewedAt = reviewedAt;
  for (const button of card.querySelectorAll('[data-choice]')) {
    button.setAttribute('aria-pressed', String(button.dataset.choice === choice));
  }
  status.textContent = `${cards.filter(item => item.dataset.choice).length} of ${cards.length} voted`;
}
document.addEventListener('click', event => {
  const button = event.target.closest('.choices button');
  if (button) setChoice(button.closest('.pair'), button.dataset.choice, new Date().toISOString());
});
document.querySelector('#save').addEventListener('click', () => {
  const rows = cards.map(card => ({id: card.dataset.id, group: Number(card.dataset.group),
    left_sha256: card.dataset.left, right_sha256: card.dataset.right,
    choice: card.dataset.choice || '', reviewed_at: card.dataset.reviewedAt || ''}));
  const payload = {schema_version: 1, method: 'direct_pair_choice', orientation_seed: orientationSeed,
    exported_at: new Date().toISOString(), rows};
  const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2) + '\\n'],
    {type: 'application/json'}));
  const link = document.createElement('a');
  link.href = url; link.download = 'photo-pair-votes.json'; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
document.querySelector('#load').addEventListener('change', async event => {
  const file = event.target.files[0];
  if (!file) return;
  try {
    const payload = JSON.parse(await file.text());
    if (payload.schema_version !== 1 || payload.method !== 'direct_pair_choice' ||
        (payload.orientation_seed ?? null) !== orientationSeed ||
        !Array.isArray(payload.rows)) throw new Error('Unsupported votes file');
    const current = new Map(cards.map(card => [card.dataset.id, card]));
    const seen = new Set();
    for (const row of payload.rows) {
      const card = current.get(row.id);
      if (!card || seen.has(row.id) || row.group !== Number(card.dataset.group) ||
          row.left_sha256 !== card.dataset.left || row.right_sha256 !== card.dataset.right ||
          typeof row.choice !== 'string' || (row.choice && !choices.has(row.choice)) ||
          typeof row.reviewed_at !== 'string') throw new Error('Votes do not match this report');
      seen.add(row.id);
    }
    if (seen.size !== cards.length) throw new Error('Votes do not cover this report');
    for (const row of payload.rows) setChoice(current.get(row.id), row.choice, row.reviewed_at);
    status.textContent += ' (loaded)';
  } catch (error) { status.textContent = error.message; }
  event.target.value = '';
});
</script></html>"""

def main():
    parser = argparse.ArgumentParser(description="Make an offline direct pair reviewer from a local photo report.")
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-opponents", type=int, default=4)
    parser.add_argument("--orientation-seed", type=int,
                        help="Shuffle pair order and left/right placement repeatably")
    args = parser.parse_args()
    report = args.report.resolve()
    default_name = "pair-review-shuffled.html" if args.orientation_seed is not None else "pair-review.html"
    output = (args.output or report / default_name).resolve()
    repo = Path(__file__).resolve().parent
    if not 1 <= args.max_opponents <= 20:
        parser.error("Choose 1 to 20 opponents per group")
    if args.orientation_seed is not None and abs(args.orientation_seed) > 2**53 - 1:
        parser.error("Orientation seed must fit an exact browser integer")
    if output.parent != report:
        parser.error("Save the page beside the report thumbnails")
    if output.is_relative_to(repo) and not any(output.is_relative_to(repo / name)
                                               for name in ("data", "outputs")):
        parser.error("Save private review pages under ignored data/ or outputs/, or outside this repo")
    if output.exists():
        parser.error("Choose a new output name to preserve the earlier review page")
    try:
        pairs = make_pairs(report, args.max_opponents, args.orientation_seed)
        output.write_text(render_page(pairs, args.orientation_seed), encoding="utf-8")
    except (OSError, ValueError, KeyError) as error:
        parser.exit(2, f"{error}\n")
    print(f"{len(pairs)} comparisons: {output}")

if __name__ == "__main__":
    main()
