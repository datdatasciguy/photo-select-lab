import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from pair_review import make_pairs
from prepare_pairs import shoot_split

def read_votes(shoot, report, votes, max_opponents):
    pairs = make_pairs(Path(report), max_opponents)
    expected = {pair["id"]: pair for pair in pairs}
    payload = json.loads(Path(votes).read_text(encoding="utf-8"))
    if (payload.get("schema_version") != 1 or payload.get("method") != "direct_pair_choice"
            or not isinstance(payload.get("rows"), list)):
        raise ValueError(f"{shoot}: unsupported direct-votes file")
    choices = {}
    for row in payload["rows"]:
        if not isinstance(row, dict):
            raise ValueError(f"{shoot}: malformed vote row")
        pair = expected.get(row.get("id"))
        choice = row.get("choice")
        if (pair is None or row["id"] in choices or row.get("group") != pair["group"]
                or row.get("left_sha256") != pair["left"]["sha256"]
                or row.get("right_sha256") != pair["right"]["sha256"]
                or choice not in {"", "left", "right", "tie", "unsure"}
                or not isinstance(row.get("reviewed_at"), str)):
            raise ValueError(f"{shoot}: votes do not match the report")
        choices[row["id"]] = choice
    if set(choices) != set(expected):
        raise ValueError(f"{shoot}: votes do not cover every comparison")
    return pairs, choices

def prepare(shoots, validation_share=0.2, seed=42, max_opponents=4):
    if not 0 <= validation_share < 1:
        raise ValueError("Validation share must be at least 0 and below 1")
    if not 1 <= max_opponents <= 20:
        raise ValueError("Choose 1 to 20 opponents per group")
    if not shoots or len({shoot for shoot, _, _ in shoots}) != len(shoots):
        raise ValueError("Choose distinct shoot IDs")
    result = []
    splits = {}
    image_splits = {}
    counts = {choice: 0 for choice in ("left", "right", "tie", "unsure", "")}
    for shoot, report, votes in shoots:
        if not shoot.strip():
            raise ValueError("Shoot ID cannot be empty")
        split = shoot_split(shoot, validation_share, seed)
        splits[shoot] = split
        with (Path(report) / "manifest.csv").open(encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream):
                previous = image_splits.setdefault(row["sha256"], split)
                if previous != split:
                    raise ValueError("An identical image appears in both train and validation shoots")
        pairs, choices = read_votes(shoot, report, votes, max_opponents)
        for pair in pairs:
            choice = choices[pair["id"]]
            counts[choice] += 1
            if choice not in {"left", "right"}:
                continue
            preferred = pair[choice]
            other = pair["right" if choice == "left" else "left"]
            result.append({"shoot": shoot, "split": split, "group": pair["group"],
                           "preferred_file": preferred["file"],
                           "preferred_sha256": preferred["sha256"],
                           "other_file": other["file"],
                           "other_sha256": other["sha256"]})
    return {"schema_version": 1, "method": "direct_pair_choice",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "validation_share": validation_share, "seed": seed,
            "max_opponents": max_opponents, "shoot_splits": splits,
            "vote_counts": counts,
            "train_pairs": sum(pair["split"] == "train" for pair in result),
            "validation_pairs": sum(pair["split"] == "validation" for pair in result),
            "pairs": result}

def main():
    parser = argparse.ArgumentParser(description="Prepare direct photo votes for the local ranker.")
    parser.add_argument("--shoot", nargs=3, action="append", metavar=("ID", "REPORT", "VOTES"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--validation-share", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-opponents", type=int, default=4)
    args = parser.parse_args()
    output = args.output.resolve()
    repo = Path(__file__).resolve().parent
    if output.is_relative_to(repo) and not any(output.is_relative_to(repo / name)
                                               for name in ("data", "outputs")):
        parser.error("Save vote-derived pairs under ignored data/ or outputs/, or outside this repo")
    if output.exists():
        parser.error("Choose a new output path to preserve earlier pairs")
    try:
        result = prepare(args.shoot, args.validation_share, args.seed, args.max_opponents)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f"{error}\n")
    print(f"{result['train_pairs']} train and {result['validation_pairs']} validation pairs: {output}")

if __name__ == "__main__":
    main()
