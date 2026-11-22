"""Run from project root using python -m ml.train_model."""

import argparse
import hashlib
import json
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    precision_recall_fscore_support,
)
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import make_pipeline
from sklearn.svm import LinearSVC
from netsense.classifier import normalize

ROOT = Path(__file__).resolve().parents[1]


def evaluate(y, scores, threshold):
    pred = np.where(scores >= threshold, "CRITICAL", "NORMAL")
    p, r, f, _ = precision_recall_fscore_support(
        y, pred, average="binary", pos_label="CRITICAL", zero_division=0
    )
    return dict(
        accuracy=accuracy_score(y, pred),
        precision=p,
        recall=r,
        f1=f,
        confusion_matrix=confusion_matrix(
            y, pred, labels=["CRITICAL", "NORMAL"]
        ).tolist(),
    )


def measure(model, kind, part):
    start = time.perf_counter()
    scores = [
        (
            -model.decision_function([s])[0]
            if kind == "margin"
            else model.predict_proba([s])[0, 0]
        )
        for s in part.text
    ]
    return np.array(scores), 1000 * (time.perf_counter() - start) / len(scores)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--thresholds",
        nargs="+",
        type=float,
        default=[0.35, 0.40, 0.45, 0.48, 0.50, 0.55],
    )
    thresholds = parser.parse_args().thresholds
    if not all(0 < t < 1 for t in thresholds):
        parser.error("Probability thresholds must lie between 0 and 1.")
    train_model(thresholds)


def train_model(thresholds=(0.35,0.4,0.45,0.48), feedback=()):
    source = ROOT / "data/messages.csv"
    data = pd.read_csv(source)
    assert not data.isna().any().any() and not data.text.duplicated().any()
    groups = data.drop_duplicates("scenario")

    def split(g, size):
        return train_test_split(
            g, test_size=size, random_state=42, stratify=g.domain + g.label
        )

    train, held = split(groups, 0.4)
    val, test = split(held, 0.5)
    train, val, test = [
        data[data.scenario.isin(g.scenario)] for g in (train, val, test)
    ]
    reserved = {normalize(t) for t in [*val.text, *test.text]}
    updates = [r for r in feedback if normalize(r["text"]) not in reserved]
    if updates:
        train = pd.concat([train,pd.DataFrame(updates)]).drop_duplicates("text",keep="last")
    report = {
        "trained_at": time.time(),
        "feedback_included": len(updates),
        "rows": len(data),
        "split_sizes": [len(p) for p in (train, val, test)],
        "validation": {},
    }
    candidates = {}
    for name, estimator in [
        ("LogisticRegression", LogisticRegression(random_state=42)),
        ("MultinomialNB", MultinomialNB()),
        ("LinearSVC", LinearSVC(random_state=42)),
    ]:
        pipe = make_pipeline(
            TfidfVectorizer(
                preprocessor=normalize, ngram_range=(1, 2), sublinear_tf=True
            ),
            estimator,
        )
        start = time.perf_counter()
        pipe.fit(train.text, train.label)
        fit_ms = 1000 * (time.perf_counter() - start)
        kind = "margin" if name == "LinearSVC" else "probability"
        scores, inference = measure(pipe, kind, val)
        options = []
        for t in ([-0.2, 0, 0.2] if kind == "margin" else thresholds):
            metrics = evaluate(val.label, scores, t)
            # Penalize excessive false alarms before optimizing recall.
            rank = (
                metrics["precision"] >= 0.75,
                metrics["recall"],
                metrics["precision"],
            )
            options.append(
                (rank, -abs(t - (0 if kind == "margin" else 0.5)), t, metrics)
            )
        rank, _, t, metrics = max(options, key=lambda x: x[:2])
        report["validation"][name] = dict(
            **metrics, threshold=t, fit_ms=fit_ms, inference_ms=inference
        )
        candidates[name] = (
            rank + (inference < 5, name == "LogisticRegression", -inference),
            pipe,
            kind,
            t,
        )
    name = max(candidates, key=lambda n: candidates[n][0])
    _, pipe, kind, t = candidates[name]
    scores, ms = measure(pipe, kind, test)
    version = (
        name + "-" + hashlib.sha256(source.read_bytes()).hexdigest()[:8] + f"-{t:g}"
    )
    report.update(
        selected=name,
        version=version,
        threshold=t,
        score_kind=kind,
        test=dict(**evaluate(test.label, scores, t), inference_ms=ms),
    )
    report["validation_scores"] = list(measure(pipe,kind,val)[0])
    report["validation_labels"] = list(val.label)
    joblib.dump(
        dict(pipeline=pipe, kind=kind, threshold=t, version=version),
        ROOT / "artifacts/trained_model.joblib",
        compress=3,
    )
    (ROOT / "ml/model_metadata.json").write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    main()
