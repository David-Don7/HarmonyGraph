"""Metrics keep unjudged results distinct from explicit negative judgments."""

import math
import numpy as np
from sklearn.metrics import cohen_kappa_score


def retrieval_metrics(ranked, judgments):
    grades = [judgments.get(item) for item in ranked]
    positives = sum(value > 0 for value in judgments.values())
    out = {
        "judgment_coverage": sum(g is not None for g in grades) / max(len(grades), 1),
        "judged_relevant_pool": positives,
    }
    for k in (5, 10, 100):
        relevant = sum(g is not None and g > 0 for g in grades[:k])
        if k <= 10:
            out[f"precision@{k}"] = relevant / k
        if k >= 10:
            out[f"pooled_recall@{k}"] = relevant / positives if positives else None
    hits, ap, reciprocal = 0, 0.0, 0.0
    for rank, grade in enumerate(grades, 1):
        if grade is not None and grade > 0:
            hits += 1
            ap += hits / rank
            if not reciprocal:
                reciprocal = 1 / rank
    out["mrr"] = reciprocal if positives else None
    out["map"] = ap / positives if positives else None
    dcg = sum((2 ** (grade or 0) - 1) / math.log2(i + 2) for i, grade in enumerate(grades[:10]))
    ideal = sum(
        (2**grade - 1) / math.log2(i + 2) for i, grade in enumerate(sorted(judgments.values(), reverse=True)[:10])
    )
    out["ndcg@10"] = dcg / ideal if ideal else None
    out["unjudged_count"] = sum(g is None for g in grades)
    return out


def uncertainty_metrics(probabilities, labels, top_k=3):
    probabilities = np.asarray(probabilities, dtype=float)
    labels = np.asarray(labels, dtype=int)
    if not len(labels):
        return {"available": False, "reason": "No aligned reference key annotations"}
    truth = np.eye(probabilities.shape[1])[labels]
    confidence = probabilities.max(axis=1)
    correct = probabilities.argmax(axis=1) == labels
    ece = 0.0
    for i in range(10):
        chosen = (confidence >= i / 10) & (confidence < (i + 1) / 10 if i < 9 else confidence <= 1)
        if chosen.any():
            ece += chosen.mean() * abs(correct[chosen].mean() - confidence[chosen].mean())
    return {
        "available": True,
        "local_key_accuracy": float(correct.mean()),
        "nll": float(-np.log(np.clip(probabilities[np.arange(len(labels)), labels], 1e-12, 1)).mean()),
        "brier": float(((probabilities - truth) ** 2).sum(axis=1).mean()),
        "ece": float(ece),
        "top_k_coverage": float(
            np.mean([label in np.argsort(row)[-top_k:] for row, label in zip(probabilities, labels)])
        ),
    }


def boundary_metrics(predicted, reference, tolerance=1):
    remaining = set(reference)
    matched = 0
    for position in sorted(set(predicted)):
        eligible = [r for r in remaining if abs(r - position) <= tolerance]
        if eligible:
            remaining.remove(min(eligible, key=lambda r: abs(r - position)))
            matched += 1
    precision = matched / len(set(predicted)) if predicted else 0.0
    recall = matched / len(set(reference)) if reference else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
    }


def bootstrap(values, seed=42, samples=2000):
    values = np.asarray([v for v in values if v is not None], dtype=float)
    if not len(values):
        return {"mean": None, "low": None, "high": None, "n": 0}
    rng = np.random.default_rng(seed)
    means = values[rng.integers(0, len(values), size=(samples, len(values)))].mean(axis=1)
    return {
        "mean": float(values.mean()),
        "low": float(np.quantile(means, 0.025)),
        "high": float(np.quantile(means, 0.975)),
        "n": len(values),
    }


def paired_comparison(first, second, seed=42):
    differences = [a - b for a, b in zip(first, second) if a is not None and b is not None]
    return {"difference_95ci": bootstrap(differences, seed), "method": "paired query bootstrap"}


def agreement(rows):
    """Rows map item IDs to annotator/grade dictionaries; incomplete nominal alpha supported."""
    complete = [list(values.values()) for values in rows.values() if len(values) >= 2]
    annotators = sorted({a for values in rows.values() for a in values})
    kappa = None
    if len(annotators) == 2:
        pairs = [(v[annotators[0]], v[annotators[1]]) for v in rows.values() if all(a in v for a in annotators)]
        if pairs:
            first, second = zip(*pairs)
            value = cohen_kappa_score(first, second, labels=[0, 1, 2])
            kappa = float(value) if np.isfinite(value) else None
    # Coincidence matrix weights each item by 1/(number of observed ratings - 1).
    coincidence = np.zeros((3, 3))
    for values in complete:
        for i, a in enumerate(values):
            for j, b in enumerate(values):
                if i != j:
                    coincidence[a, b] += 1 / (len(values) - 1)
    total = coincidence.sum()
    alpha = None
    if total > 1:
        observed = (total - np.trace(coincidence)) / total
        marginals = coincidence.sum(axis=0)
        expected = (total**2 - np.sum(marginals**2)) / (total * (total - 1))
        if expected:
            alpha = float(1 - observed / expected)
    return {
        "cohen_kappa": kappa,
        "krippendorff_alpha_nominal": alpha,
        "overlapping_items": len(complete),
        "annotators": len(annotators),
    }
