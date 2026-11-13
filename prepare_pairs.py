import argparse
import csv
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

def read_shoot(shoot, report, labels):
    with (Path(report) / "manifest.csv").open(encoding="utf-8", newline="") as stream:
        source_rows = list(csv.DictReader(stream))
    manifest = {row["file"]: row for row in source_rows}
    if not source_rows or len(manifest) != len(source_rows):
        raise ValueError(f"{shoot}: empty report or duplicate filenames")
    payload = json.loads(Path(labels).read_text(encoding="utf-8"))
    if (not isinstance(payload, dict) or payload.get("schema_version") != 1
            or not isinstance(payload.get("rows"), list)):
        raise ValueError(f"{shoot}: unsupported label file")
    choices = {}
    for row in payload["rows"]:
        if not isinstance(row, dict) or not isinstance(row.get("file"), str):
            raise ValueError(f"{shoot}: malformed label row")
        file = row["file"]
        source = manifest.get(file)
        label = row.get("label")
        if (file in choices or source is None or row.get("sha256") != source["sha256"]
                or row.get("group") != int(source["group"])
                or row.get("rank") != int(source["rank"])
                or not isinstance(label, str)
                or label not in {"", "keep", "reject", "unsure"}):
            raise ValueError(f"{shoot}: labels do not match the report")
        choices[file] = {**source, "label": label}
    if set(choices) != set(manifest):
        raise ValueError(f"{shoot}: labels do not cover every report image")
    return list(choices.values())

def shoot_split(shoot, validation_share, seed):
    digest = hashlib.sha256(f"{seed}:{shoot}".encode("utf-8")).digest()
    fraction = int.from_bytes(digest[:8], "big") / 2**64
    return "validation" if fraction < validation_share else "train"

def prepare(shoots, validation_share=0.2, seed=42):
    if not 0 <= validation_share < 1:
        raise ValueError("Validation share must be at least 0 and below 1")
    if not shoots or len({shoot for shoot, _, _ in shoots}) != len(shoots):
        raise ValueError("Choose distinct shoot IDs")
    pairs = []
    skipped_identical = 0
    labeled = 0
    splits = {}
    image_splits = {}
    for shoot, report, labels in shoots:
        if not shoot.strip():
            raise ValueError("Shoot ID cannot be empty")
        rows = read_shoot(shoot, report, labels)
        split = shoot_split(shoot, validation_share, seed)
        splits[shoot] = split
        for row in rows:
            previous = image_splits.setdefault(row["sha256"], split)
            if previous != split:
                raise ValueError("An identical image appears in both train and validation shoots")
        labeled += sum(row["label"] in {"keep", "reject", "unsure"} for row in rows)
        groups = defaultdict(list)
        for row in rows:
            groups[int(row["group"])].append(row)
        for group, members in groups.items():
            seen = set()
            for kept in (row for row in members if row["label"] == "keep"):
                for rejected in (row for row in members if row["label"] == "reject"):
                    key = (kept["sha256"], rejected["sha256"])
                    if kept["sha256"] == rejected["sha256"]:
                        skipped_identical += 1
                    elif key not in seen:
                        pairs.append({"shoot": shoot, "split": split, "group": group,
                                      "preferred_file": kept["file"], "preferred_sha256": kept["sha256"],
                                      "other_file": rejected["file"], "other_sha256": rejected["sha256"]})
                        seen.add(key)
    return {"schema_version": 1, "method": "keep_over_reject_within_group",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "validation_share": validation_share, "seed": seed, "shoot_splits": splits,
            "reviewed_images": labeled, "identical_pairs_skipped": skipped_identical,
            "train_pairs": sum(row["split"] == "train" for row in pairs),
            "validation_pairs": sum(row["split"] == "validation" for row in pairs),
            "pairs": pairs}

def main():
    parser = argparse.ArgumentParser(description="Make local photo preference pairs from review labels.")
    parser.add_argument("--shoot", nargs=3, action="append", metavar=("ID", "REPORT", "LABELS"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--validation-share", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    output = args.output.resolve()
    repo = Path(__file__).resolve().parent
    if output.is_relative_to(repo) and not any(output.is_relative_to(repo / name) for name in ("data", "outputs")):
        parser.error("Save label-derived pairs under ignored data/ or outputs/, or outside this repo")
    if output.exists():
        parser.error("Choose a new output path to preserve earlier pairs")
    try:
        result = prepare(args.shoot, args.validation_share, args.seed)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError) as error:
        parser.exit(2, f"{error}\n")
    print(f"{result['train_pairs']} train and {result['validation_pairs']} validation pairs: {output}")

if __name__ == "__main__":
    main()
