import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

def evaluate(features, model, source_digest):
    if (features.get("schema_version") != 1 or model.get("schema_version") != 1
            or model.get("model") != "linear_pairwise_logistic"
            or model.get("feature_input_sha256") != source_digest
            or model.get("feature_names") != features.get("feature_names")
            or model.get("scaling") != features.get("scaling")):
        raise ValueError("Model and prepared features do not describe the same input")
    names = features["feature_names"]
    weights = model.get("weights")
    if (not isinstance(weights, list) or len(weights) != len(names)
            or not all(isinstance(value, (int, float)) and math.isfinite(value)
                       for value in weights)):
        raise ValueError("Model coefficients are missing or invalid")
    sharpness = names.index("sharpness")
    by_shoot = defaultdict(lambda: {"pairs": 0, "model_higher": 0,
                                   "sharpness_higher": 0, "sharpness_ties": 0})
    disagreements = []
    for pair in features["pairs"]:
        if pair["split"] != "validation":
            continue
        preferred, other = pair["preferred"], pair["other"]
        if (len(preferred) != len(names) or len(other) != len(names)
                or not all(math.isfinite(value) for value in preferred + other)):
            raise ValueError("Invalid validation feature vector")
        difference = [left - right for left, right in zip(preferred, other)]
        model_margin = sum(weight * value for weight, value in zip(weights, difference))
        sharpness_margin = difference[sharpness]
        if not math.isfinite(model_margin):
            raise ValueError("Nonfinite model score")
        model_higher = model_margin > 0
        sharpness_higher = sharpness_margin > 0
        counts = by_shoot[pair["shoot"]]
        counts["pairs"] += 1
        counts["model_higher"] += model_higher
        counts["sharpness_higher"] += sharpness_higher
        counts["sharpness_ties"] += sharpness_margin == 0
        if model_higher != sharpness_higher or sharpness_margin == 0:
            disagreements.append({"shoot": pair["shoot"], "group": pair["group"],
                                  "preferred_file": pair["preferred_file"],
                                  "other_file": pair["other_file"],
                                  "model_margin": model_margin,
                                  "sharpness_margin": sharpness_margin})
    totals = {key: sum(row[key] for row in by_shoot.values())
              for key in ("pairs", "model_higher", "sharpness_higher", "sharpness_ties")}
    if totals["pairs"] != features.get("validation_pairs") or totals["pairs"] != model.get("validation_pairs"):
        raise ValueError("Validation pair count does not match the prepared data and model")
    method = features.get("method", "keep_over_reject_within_group")
    label_method = ("Direct left/right votes" if method == "direct_pair_choice"
                    else "Keep-over-Reject within groups; not direct pairwise votes")
    return {"schema_version": 1, "scope": "held_out_validation_pairs",
            "status": "diagnostic_only" if totals["pairs"] else "no_validation_pairs",
            "method": label_method,
            "validation_shoots": len(by_shoot), "totals": totals,
            "by_shoot": dict(sorted(by_shoot.items())),
            "disagreements": disagreements,
            "limitation": "Counts are not a real-photo quality claim without enough independently reviewed shoots and pairs."}

def main():
    parser = argparse.ArgumentParser(description="Compare a local preference ranker with sharpness on held-out pairs.")
    parser.add_argument("features", type=Path)
    parser.add_argument("model", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    repo = Path(__file__).resolve().parent
    if output.is_relative_to(repo) and not any(output.is_relative_to(repo / name)
                                               for name in ("data", "outputs")):
        parser.error("Save review output under ignored data/ or outputs/, or outside this repo")
    if output.exists():
        parser.error("Choose a new output path to preserve earlier reviews")
    try:
        source = args.features.read_bytes()
        features = json.loads(source)
        model = json.loads(args.model.read_text(encoding="utf-8"))
        report = evaluate(features, model, hashlib.sha256(source).hexdigest())
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f"{error}\n")
    print(f"{report['totals']['pairs']} validation pairs from {report['validation_shoots']} shoots: {output}")
    print("Diagnostic counts only; review real labels before reporting ranking quality.")

if __name__ == "__main__":
    main()
