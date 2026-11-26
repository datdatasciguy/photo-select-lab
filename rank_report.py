import argparse
import csv
import json
import math
import re
from collections import defaultdict
from html import escape
from pathlib import Path
from random import Random

from preference_features import FEATURES, load_report

def score_report(report, model):
    if (model.get("schema_version") != 1 or model.get("model") != "linear_pairwise_logistic"
            or model.get("feature_names") != list(FEATURES)):
        raise ValueError("Model feature names do not match this report")
    scaling = model.get("scaling", {})
    means, scales, weights = scaling.get("mean"), scaling.get("scale"), model.get("weights")
    if scaling.get("fit_split") != "train":
        raise ValueError("Model scaling was not fitted on training images")
    if not all(isinstance(values, list) and len(values) == len(FEATURES)
               for values in (means, scales, weights)):
        raise ValueError("Model coefficients or feature scales are incomplete")
    if (not all(isinstance(value, (int, float)) and math.isfinite(value)
                for values in (means, scales, weights) for value in values)
            or any(scale <= 0 for scale in scales)):
        raise ValueError("Model coefficients or feature scales are invalid")

    images = load_report(report)
    grouped = defaultdict(list)
    with (report / "manifest.csv").open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            image = images[row["file"]]
            digest = image["sha256"]
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError("Invalid image digest in report")
            if not (report / "thumbnails" / f"{digest}.jpg").is_file():
                raise ValueError("A report thumbnail is missing")
            normalized = [(value - mean) / scale
                          for value, mean, scale in zip(image["values"], means, scales)]
            score = sum(weight * value for weight, value in zip(weights, normalized))
            if not math.isfinite(score):
                raise ValueError("Nonfinite model score")
            grouped[image["group"]].append({"file": row["file"], "sha256": digest,
                                            "baseline_rank": int(row["rank"]), "score": score})
    for rows in grouped.values():
        rows.sort(key=lambda row: (-row["score"], row["baseline_rank"], row["file"]))
    return dict(sorted(grouped.items()))

def format_html(grouped, model, shuffle=False, seed=42):
    sections = []
    rng = Random(seed)
    for group, rows in grouped.items():
        rows = list(rows)
        if shuffle:
            rng.shuffle(rows)
        cards = []
        for model_rank, row in enumerate(rows, 1):
            name = escape(row["file"])
            order = ("Shuffled review" if shuffle else
                     f'Model #{model_rank} · Original #{row["baseline_rank"]} · Score {row["score"]:.3f}')
            cards.append(f'<article class="review-card" data-file="{escape(row["file"], quote=True)}" '
                         f'data-sha256="{row["sha256"]}" data-group="{group}" '
                         f'data-rank="{row["baseline_rank"]}">'
                         f'<img src="thumbnails/{row["sha256"]}.jpg" alt="{name}">'
                         f'<div><strong>{name}</strong><p>{order}</p>'
                         '<div class="choices" role="group" aria-label="Review choice">'
                         '<button type="button" data-choice="keep">Keep</button>'
                         '<button type="button" data-choice="reject">Reject</button>'
                         '<button type="button" data-choice="unsure">Unsure</button>'
                         '</div></div></article>')
        sections.append(f'<section><h2>Group {group} <small>{len(rows)} images</small></h2>'
                        f'<div class="grid">{"".join(cards)}</div></section>')
    method = ("direct pair votes" if model.get("method") == "direct_pair_choice"
              else "Keep/Reject-derived pairs" if model.get("method") == "keep_over_reject_within_group"
              else "earlier pair export")
    intro = (f"Images are shuffled within each group using seed {seed}. Model scores and "
             "original ranks are hidden while you choose; filenames can still influence review. "
             "The saved labels keep the original ranks for validation." if shuffle else
             "Images appear in model order within each report group. Original # is the earlier "
             "sharpness-based review order. Scores are relative to this saved model, not "
             "calibrated photo quality.")
    model_note = ("Ranking details are hidden during this review." if shuffle else
                  f"Model input: {escape(method)} · {escape(str(model.get('train_pairs', 0)))} training "
                  f"pairs · {escape(str(model.get('validation_pairs', 0)))} validation pairs. "
                  "Inspect real held-out choices before judging whether model order helps.")
    return f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Local ranking review</title>
<style>
body{{font:16px/1.5 system-ui,sans-serif;max-width:1150px;margin:auto;padding:24px;background:#f3f5f5;color:#1c2c33}}
p{{max-width:78ch}}section{{margin:28px 0}}small{{font-weight:normal;color:#66777f}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:14px}}
article{{background:white;border:1px solid #d3dddf;border-radius:8px;overflow:hidden}}
img{{width:100%;height:190px;object-fit:contain;background:#e6ebed}}
article div{{padding:12px;overflow-wrap:anywhere}}article p{{font-size:13px;margin:6px 0 0}}
.toolbar,.choices{{display:flex;gap:8px;flex-wrap:wrap;align-items:center}}.toolbar{{margin:20px 0}}
button,.load{{font:inherit;border:1px solid #69818c;border-radius:6px;padding:7px 12px;background:white;cursor:pointer}}
.load input{{display:none}}.choices button[aria-pressed=true]{{background:#195e70;color:white}}
</style><h1>Local ranking review</h1>
<p>{intro} Keep the original report and photos local.</p>
<p>{model_note}</p>
<p>Choose Keep, Reject, or Unsure and save labels before closing this page. Review independent held-out images before judging ranking quality.</p>
<div class="toolbar"><button type="button" id="save">Save labels JSON</button>
<label class="load">Load labels JSON<input id="load" type="file" accept=".json,application/json"></label>
<span id="status" role="status" aria-live="polite">No labels yet</span></div>
{''.join(sections)}<script>
const cards = [...document.querySelectorAll('.review-card')];
const status = document.querySelector('#status');
const choices = new Set(['keep', 'reject', 'unsure']);
function setChoice(card, choice, reviewedAt) {{
  card.dataset.choice = choice;
  card.dataset.reviewedAt = reviewedAt;
  for (const button of card.querySelectorAll('[data-choice]')) {{
    button.setAttribute('aria-pressed', String(button.dataset.choice === choice));
  }}
  status.textContent = `${{cards.filter(item => item.dataset.choice).length}} of ${{cards.length}} labeled`;
}}
document.addEventListener('click', event => {{
  const button = event.target.closest('.choices button');
  if (button) setChoice(button.closest('.review-card'), button.dataset.choice, new Date().toISOString());
}});
document.querySelector('#save').addEventListener('click', () => {{
  const rows = cards.map(card => ({{file: card.dataset.file, sha256: card.dataset.sha256,
    group: Number(card.dataset.group), rank: Number(card.dataset.rank),
    label: card.dataset.choice || '', reviewed_at: card.dataset.reviewedAt || ''}}));
  const payload = {{schema_version: 1, exported_at: new Date().toISOString(), rows}};
  const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2) + '\\n'],
    {{type: 'application/json'}}));
  const link = document.createElement('a');
  link.href = url; link.download = 'photo-review-labels.json'; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}});
document.querySelector('#load').addEventListener('change', async event => {{
  const file = event.target.files[0];
  if (!file) return;
  try {{
    const payload = JSON.parse(await file.text());
    if (payload.schema_version !== 1 || !Array.isArray(payload.rows))
      throw new Error('Unsupported labels file');
    const current = new Map(cards.map(card => [card.dataset.file + ':' + card.dataset.sha256, card]));
    const seen = new Set();
    for (const row of payload.rows) {{
      const key = row.file + ':' + row.sha256;
      const card = current.get(key);
      if (!card || seen.has(key) || row.group !== Number(card.dataset.group) ||
          row.rank !== Number(card.dataset.rank) || typeof row.label !== 'string' ||
          (row.label && !choices.has(row.label)) || typeof row.reviewed_at !== 'string')
        throw new Error('Labels do not match this report');
      seen.add(key);
    }}
    if (seen.size !== cards.length) throw new Error('Labels do not match this report');
    for (const row of payload.rows) {{
      setChoice(current.get(row.file + ':' + row.sha256), row.label, row.reviewed_at);
    }}
    status.textContent += ' (loaded)';
  }} catch (error) {{
    status.textContent = error.message;
  }}
  event.target.value = '';
}});
</script></html>"""

def main():
    parser = argparse.ArgumentParser(description="Inspect local photo model order beside original report rank.")
    parser.add_argument("report", type=Path)
    parser.add_argument("model", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--shuffle", action="store_true",
                        help="Shuffle each group and hide rank and score while reviewing")
    parser.add_argument("--seed", type=int, default=42,
                        help="Repeatable shuffle seed (default: 42)")
    args = parser.parse_args()
    report = args.report.resolve()
    default_name = "shuffled-review.html" if args.shuffle else "ranker-review.html"
    output = (args.output or report / default_name).resolve()
    repo = Path(__file__).resolve().parent
    if output.parent != report:
        parser.error("Save the page beside the report thumbnails")
    if output.is_relative_to(repo) and not any(output.is_relative_to(repo / name)
                                               for name in ("data", "outputs")):
        parser.error("Save ranking pages under ignored data/ or outputs/, or outside this repo")
    if output.exists():
        parser.error("Choose a new output name to preserve earlier ranking pages")
    try:
        model = json.loads(args.model.read_text(encoding="utf-8"))
        grouped = score_report(report, model)
        output.write_text(format_html(grouped, model, args.shuffle, args.seed), encoding="utf-8")
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f"{error}\n")
    print(f"{sum(len(rows) for rows in grouped.values())} images in {len(grouped)} groups: {output}")

if __name__ == "__main__":
    main()
