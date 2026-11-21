import argparse
import csv
import json
import math
from pathlib import Path

FEATURES = ("aspect", "sharpness", "mean_luma", "dark_fraction", "bright_fraction")

def load_report(folder):
    with (Path(folder) / "manifest.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError(f"Empty report: {folder}")
    images = {}
    for row in rows:
        name = row["file"]
        if name in images:
            raise ValueError(f"Duplicate report filename: {name}")
        width, height = float(row["width"]), float(row["height"])
        if not math.isfinite(width) or not math.isfinite(height) or height <= 0:
            raise ValueError(f"Invalid image dimensions: {name}")
        values = [width / height] + [float(row[feature]) for feature in FEATURES[1:]]
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"Nonfinite image feature: {name}")
        images[name] = {"sha256": row["sha256"], "group": int(row["group"]),
                        "values": values}
    return images

def prepare_features(pairs_path, reports):
    payload = json.loads(Path(pairs_path).read_text(encoding="utf-8"))
    if (payload.get("schema_version") != 1
            or payload.get("method") not in (None, "keep_over_reject_within_group", "direct_pair_choice")
            or not isinstance(payload.get("pairs"), list)):
        raise ValueError("Expected a version 1 reviewed pairs file")
    if not payload["pairs"]:
        raise ValueError("No reviewed pairs to prepare")
    report_rows = {shoot: load_report(folder) for shoot, folder in reports.items()}
    if set(payload["shoot_splits"]) != set(report_rows):
        raise ValueError("Supply one report for every shoot in the pairs file")
    prepared = []
    digest_splits = {}
    training_images = {}
    for pair in payload["pairs"]:
        shoot = pair["shoot"]
        split = pair["split"]
        if split not in {"train", "validation"} or split != payload["shoot_splits"].get(shoot):
            raise ValueError("Pair split does not match its shoot")
        sides = []
        for role in ("preferred", "other"):
            name = pair[f"{role}_file"]
            row = report_rows[shoot].get(name)
            if (row is None or row["sha256"] != pair[f"{role}_sha256"]
                    or row["group"] != pair["group"]):
                raise ValueError(f"Pair does not match report: {shoot}/{name}")
            previous = digest_splits.setdefault(row["sha256"], split)
            if previous != split:
                raise ValueError("Identical image crosses train and validation")
            if split == "train":
                training_images[row["sha256"]] = row["values"]
            sides.append(row["values"])
        if pair["preferred_sha256"] == pair["other_sha256"]:
            raise ValueError("A preference pair cannot compare identical images")
        prepared.append({"shoot": shoot, "split": split, "group": pair["group"],
                         "preferred_file": pair["preferred_file"],
                         "other_file": pair["other_file"], "values": sides})
    if not training_images:
        raise ValueError("At least one training pair is needed to fit feature scales")
    columns = list(zip(*training_images.values()))
    means = [sum(column) / len(column) for column in columns]
    scales = [math.sqrt(sum((value - mean) ** 2 for value in column) / len(column)) or 1.0
              for column, mean in zip(columns, means)]
    for pair in prepared:
        left, right = pair.pop("values")
        pair["preferred"] = [(value - mean) / scale
                             for value, mean, scale in zip(left, means, scales)]
        pair["other"] = [(value - mean) / scale
                         for value, mean, scale in zip(right, means, scales)]
    return {"schema_version": 1,
            "method": payload.get("method") or "keep_over_reject_within_group",
            "feature_names": FEATURES,
            "scaling": {"fit_split": "train", "unique_train_images": len(training_images),
                        "mean": means, "scale": scales},
            "train_pairs": sum(row["split"] == "train" for row in prepared),
            "validation_pairs": sum(row["split"] == "validation" for row in prepared),
            "pairs": prepared}

def main():
    parser = argparse.ArgumentParser(description="Join reviewed photo pairs to train-scaled report features.")
    parser.add_argument("pairs", type=Path)
    parser.add_argument("--report", nargs=2, action="append", metavar=("SHOOT", "FOLDER"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reports = dict(args.report)
    if len(reports) != len(args.report):
        parser.error("Shoot IDs must be distinct")
    output = args.output.resolve()
    repo = Path(__file__).resolve().parent
    if output.is_relative_to(repo) and not any(output.is_relative_to(repo / name)
                                               for name in ("data", "outputs")):
        parser.error("Save prepared pairs under ignored data/ or outputs/, or outside this repo")
    if output.exists():
        parser.error("Choose a new output path to preserve earlier results")
    try:
        result = prepare_features(args.pairs, reports)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    except (OSError, ValueError, KeyError) as error:
        parser.exit(2, f"{error}\n")
    print(f"{result['train_pairs']} train and {result['validation_pairs']} validation pairs: {output}")

if __name__ == "__main__":
    main()
