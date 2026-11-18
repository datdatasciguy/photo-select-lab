import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np

def pair_arrays(payload):
    names = payload.get("feature_names")
    pairs = payload.get("pairs")
    if payload.get("schema_version") != 1 or not isinstance(names, list) or not names:
        raise ValueError("Expected prepared preference features, schema version 1")
    if not isinstance(pairs, list) or not pairs:
        raise ValueError("No prepared pairs found")
    if payload.get("scaling", {}).get("fit_split") != "train":
        raise ValueError("Feature scaling must be fitted on training images only")
    training = [pair for pair in pairs if pair.get("split") == "train"]
    validation = [pair for pair in pairs if pair.get("split") == "validation"]
    if len(training) + len(validation) != len(pairs) or not training:
        raise ValueError("Expected at least one training pair and only known splits")
    if sum(pair.get("split") == "train" for pair in pairs) != payload.get("train_pairs"):
        raise ValueError("Training pair count does not match the file")
    if len(validation) != payload.get("validation_pairs"):
        raise ValueError("Validation pair count does not match the file")

    def differences(rows):
        if not rows:
            return np.empty((0, len(names)), dtype=float)
        values = np.asarray([np.asarray(pair["preferred"], dtype=float)
                             - np.asarray(pair["other"], dtype=float) for pair in rows], dtype=float)
        if values.shape != (len(rows), len(names)) or not np.isfinite(values).all():
            raise ValueError("Pair features must be finite vectors of the advertised length")
        return values

    return names, training, validation, differences(training), differences(validation)

def logistic_loss(margins):
    return np.logaddexp(0, -margins)

def train(payload, epochs=300, learning_rate=0.1, l2=0.01):
    if epochs < 1 or not math.isfinite(learning_rate) or not math.isfinite(l2) or learning_rate <= 0 or l2 < 0:
        raise ValueError("Epochs and learning rate must be positive; L2 cannot be negative")
    names, training, validation, x_train, x_validation = pair_arrays(payload)
    shoots = Counter(pair["shoot"] for pair in training)
    pair_weights = np.asarray([1 / shoots[pair["shoot"]] for pair in training], dtype=float)
    pair_weights /= pair_weights.sum()
    weights = np.zeros(len(names), dtype=float)

    def objective(current):
        return float(pair_weights @ logistic_loss(x_train @ current)
                     + l2 * np.dot(current, current) / 2)

    initial_loss = objective(weights)
    for _ in range(epochs):
        margins = x_train @ weights
        wrong_probability = 1 / (1 + np.exp(np.clip(margins, -700, 700)))
        gradient = -(pair_weights * wrong_probability) @ x_train + l2 * weights
        weights -= learning_rate * gradient
        if not np.isfinite(weights).all():
            raise ValueError("Training diverged; reduce the learning rate")
    final_loss = objective(weights)
    if final_loss > initial_loss:
        raise ValueError("Training loss increased; reduce the learning rate")
    validation_margins = x_validation @ weights
    return {"schema_version": 1, "model": "linear_pairwise_logistic",
            "feature_names": names, "weights": weights.tolist(),
            "scaling": payload["scaling"], "training_shoots": len(shoots),
            "train_pairs": len(training), "validation_pairs": len(validation),
            "validation_preferred_above_other": int((validation_margins > 0).sum()),
            "epochs": epochs, "learning_rate": learning_rate, "l2": l2,
            "initial_training_loss": initial_loss, "final_training_loss": final_loss}

def main():
    parser = argparse.ArgumentParser(description="Fit a local linear preference ranker on reviewed photo pairs.")
    parser.add_argument("features", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=300)
    parser.add_argument("--learning-rate", type=float, default=0.1)
    parser.add_argument("--l2", type=float, default=0.01)
    args = parser.parse_args()
    output = args.output.resolve()
    repo = Path(__file__).resolve().parent
    if output.is_relative_to(repo) and not any(output.is_relative_to(repo / name)
                                               for name in ("data", "outputs")):
        parser.error("Save model weights under ignored data/ or outputs/, or outside this repo")
    if output.exists():
        parser.error("Choose a new output path to preserve earlier models")
    try:
        source = args.features.read_bytes()
        payload = json.loads(source)
        result = train(payload, args.epochs, args.learning_rate, args.l2)
        result["feature_input_sha256"] = hashlib.sha256(source).hexdigest()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f"{error}\n")
    print(f"Trained on {result['train_pairs']} pairs from {result['training_shoots']} shoot(s): {output}")
    print(f"Validation pairs: {result['validation_pairs']}; preferred scored higher: "
          f"{result['validation_preferred_above_other']}")

if __name__ == "__main__":
    main()
