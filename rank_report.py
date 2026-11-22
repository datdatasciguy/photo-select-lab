import argparse
import csv
import json
import math
import re
from collections import defaultdict
from html import escape
from pathlib import Path

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

def format_html(grouped, model):
    sections = []
    for group, rows in grouped.items():
        cards = []
        for model_rank, row in enumerate(rows, 1):
            name = escape(row["file"])
            cards.append(f'<article><img src="thumbnails/{row["sha256"]}.jpg" alt="{name}">'
                         f'<div><strong>{name}</strong><p>Model #{model_rank} · '
                         f'Original #{row["baseline_rank"]} · Score {row["score"]:.3f}</p></div></article>')
        sections.append(f'<section><h2>Group {group} <small>{len(rows)} images</small></h2>'
                        f'<div class="grid">{"".join(cards)}</div></section>')
    method = ("direct pair votes" if model.get("method") == "direct_pair_choice"
              else "Keep/Reject-derived pairs" if model.get("method") == "keep_over_reject_within_group"
              else "earlier pair export")
    return f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Local ranking review</title>
<style>
body{{font:16px/1.5 system-ui,sans-serif;max-width:1150px;margin:auto;padding:24px;background:#f3f5f5;color:#1c2c33}}
p{{max-width:78ch}}section{{margin:28px 0}}small{{font-weight:normal;color:#66777f}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:14px}}
article{{background:white;border:1px solid #d3dddf;border-radius:8px;overflow:hidden}}
img{{width:100%;height:190px;object-fit:contain;background:#e6ebed}}
article div{{padding:12px;overflow-wrap:anywhere}}article p{{font-size:13px;margin:6px 0 0}}
</style><h1>Local ranking review</h1>
<p>Images appear in model order within each report group. Original # is the earlier sharpness-based review order. Scores are relative to this saved model, not calibrated photo quality. Keep the original report and photos local.</p>
<p>Model input: {escape(method)} · {escape(str(model.get('train_pairs', 0)))} training pairs · {escape(str(model.get('validation_pairs', 0)))} validation pairs. Inspect real held-out choices before judging whether model order helps.</p>
{''.join(sections)}</html>"""

def main():
    parser = argparse.ArgumentParser(description="Inspect local photo model order beside original report rank.")
    parser.add_argument("report", type=Path)
    parser.add_argument("model", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = args.report.resolve()
    output = (args.output or report / "ranker-review.html").resolve()
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
        output.write_text(format_html(grouped, model), encoding="utf-8")
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f"{error}\n")
    print(f"{sum(len(rows) for rows in grouped.values())} images in {len(grouped)} groups: {output}")

if __name__ == "__main__":
    main()
