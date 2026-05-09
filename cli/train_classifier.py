"""
Train the conversation state classifier.

Reads Training data/labeled_data.csv (produced by label_conversations.py),
embeds each row using sentence-transformers, trains a LogisticRegression,
and saves the model to classifier/model.pkl.

Usage:
    python cli/train_classifier.py
"""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).parent.parent
DATA_PATH = ROOT / "Training data" / "labeled_data.csv"
MODEL_DIR = ROOT / "classifier"
MODEL_PATH = MODEL_DIR / "model.pkl"

EMBEDDER_NAME = "all-MiniLM-L6-v2"
VALID_LABELS = {"warm", "cold", "skeptical", "hostile"}


def load_data(path: pathlib.Path) -> tuple[list[str], list[str]]:
    import csv
    texts, labels = [], []
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            label = row["label"].strip().lower()
            text = row["text"].strip()
            context = json.loads(row.get("context", "[]"))

            if label not in VALID_LABELS or not text:
                continue

            # Include last 2 context turns to give the model more signal
            ctx_str = " | ".join(context[-2:]) if context else ""
            full_input = f"{ctx_str} | {text}" if ctx_str else text

            texts.append(full_input)
            labels.append(label)

    return texts, labels


def main():
    if not DATA_PATH.exists():
        print(f"Labeled data not found at {DATA_PATH}")
        print("Run 'python cli/label_conversations.py' first.")
        sys.exit(1)

    texts, labels = load_data(DATA_PATH)
    print(f"Loaded {len(texts)} labeled examples.")

    if len(texts) < 4:
        print("Not enough data to train. Need at least 4 labeled examples.")
        sys.exit(1)

    label_counts = {}
    for l in labels:
        label_counts[l] = label_counts.get(l, 0) + 1
    print(f"Label distribution: {label_counts}")

    print(f"Loading embedder '{EMBEDDER_NAME}'...")
    from sentence_transformers import SentenceTransformer
    embedder = SentenceTransformer(EMBEDDER_NAME)

    print("Embedding texts...")
    X = embedder.encode(texts, show_progress_bar=True)

    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import cross_val_score

    clf = LogisticRegression(max_iter=1000, C=1.0, random_state=42)

    # Cross-validate if we have enough data
    if len(texts) >= 10:
        scores = cross_val_score(clf, X, labels, cv=min(5, len(texts) // 2), scoring="accuracy")
        print(f"Cross-val accuracy: {scores.mean():.2f} (+/- {scores.std():.2f})")

    clf.fit(X, labels)
    print(f"Trained. Classes: {list(clf.classes_)}")

    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    import joblib
    model_data = {
        "model": clf,
        "embedder": EMBEDDER_NAME,
        "classes": list(clf.classes_),
        "trained_on": len(texts),
    }
    joblib.dump(model_data, MODEL_PATH)
    print(f"Model saved to {MODEL_PATH}")
    print("\nTo use the classifier, restart the bot — it loads automatically.")


if __name__ == "__main__":
    main()
