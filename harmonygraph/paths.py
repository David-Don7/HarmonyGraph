"""Research v2: query-independent passage paths conditioned on full chart context.

Outside-passage states are marginalized by forward/backward inference. Retained
paths are mutually exclusive assignments of every key/function inside the passage.
Beam selection is approximate; ORIGINAL probabilities are never renormalized.
"""

from __future__ import annotations

import numpy as np
from scipy.special import logsumexp

from .contracts import fingerprint
from .music import alignment, infer_keys, interpret, key_name

VERSION = "context-path-expectation-v1"


def context_messages(chords, events, config):
    return infer_keys(
        chords, [e.section_id for e in events], [e.duration for e in events], config, return_messages=True
    )


def key_paths(messages, start, end, budget):
    posterior, _, emissions, transitions, beta = messages
    beam = [((k,), float(posterior[start, k])) for k in range(24)]
    beam = sorted(beam, key=lambda item: (-item[1], item[0]))[:budget]
    for t in range(start + 1, end + 1):
        logp = transitions[t - 1] + emissions[t][None, :] + beta[t][None, :]
        conditional = np.exp(logp - logsumexp(logp, axis=1)[:, None])
        expanded = [
            (path + (k,), probability * float(conditional[path[-1], k]))
            for path, probability in beam
            for k in range(24)
        ]
        beam = sorted(expanded, key=lambda item: (-item[1], item[0]))[:budget]
    return beam


def joint_paths(chords, messages, start, end, key_budget=64, function_budget=16, hard=False):
    keys = key_paths(messages, start, end, key_budget)
    if hard:
        keys = [(tuple(messages[1][start : end + 1]), 1.0)]
    retained = []
    for key_sequence, probability in keys:
        beam = [((), 1.0)]
        for offset, key in enumerate(key_sequence):
            t = start + offset
            options = interpret(chords[t], key, chords[t + 1] if t + 1 < len(chords) else None)
            if hard:
                options = [{**options[0], "weight": 1.0}]
            expanded = [
                (sequence + (option["roman"],), weight * option["weight"])
                for sequence, weight in beam
                for option in options
            ]
            beam = sorted(expanded, key=lambda item: (-item[1], item[0]))[:function_budget]
        for sequence, weight in beam:
            retained.append(
                {"keys": list(key_sequence), "functions": list(sequence), "probability": probability * weight}
            )
    return sorted(retained, key=lambda path: (-path["probability"], path["keys"], path["functions"]))


def score_paths(query, paths, config, threshold=0.8, ranking="path_expectation"):
    evidence = []
    probabilities = [p["probability"] for p in paths]
    if ranking == "equal_paths":
        probabilities = [1 / len(paths)] * len(paths) if paths else []
    elif ranking == "shuffled_paths":
        probabilities = np.random.default_rng(config.seed).permutation(probabilities).tolist()
    for path, weight in zip(paths, probabilities):
        similarity, trace = alignment(query, path["functions"], config)
        evidence.append(
            {
                **path,
                "ranking_weight": weight,
                "key_names": [key_name(k) for k in path["keys"]],
                "similarity": similarity,
                "contribution": weight * similarity,
                "alignment": trace,
            }
        )
    mass = min(1.0, sum(p["probability"] for p in paths))
    lower = sum(p["probability"] * p["similarity"] for p in evidence)
    score = sum(p["contribution"] for p in evidence)
    if ranking == "max_path":
        score = max((p["similarity"] for p in evidence), default=0.0)
    return {
        "version": VERSION,
        "semantics": ranking,
        "score": score,
        "retained_mass": mass,
        "omitted_mass": max(0.0, 1 - mass),
        "expected_similarity_bounds": [lower, min(1.0, lower + 1 - mass)],
        "match_probability_bounds": [
            sum(p["probability"] for p in evidence if p["similarity"] >= threshold),
            min(1.0, sum(p["probability"] for p in evidence if p["similarity"] >= threshold) + 1 - mass),
        ],
        "match_threshold": threshold,
        "paths": evidence,
        "probability_note": "Normalized HMM model probabilities; function weights are unvalidated theory assumptions. Not human relevance probabilities.",
        "approximation": "Prefix key beam, then conditional function beam; not guaranteed globally highest-probability joint paths.",
        "bound_scope": "Fixed passage under this model; candidate omission is separate.",
    }


def passage_score(query, chords, events, start, end, config, request, messages):
    paths = joint_paths(
        chords, messages, start, end, request.path_budget, request.function_budget, hard=request.ranking == "hard_path"
    )
    result = score_paths(query, paths, config, request.match_threshold, request.ranking)
    result["context"] = {
        "start": 0,
        "end": len(chords) - 1,
        "evidence": "chord-only",
        "fingerprint": fingerprint([e.label for e in events]),
    }
    if request.ranking == "hard_path":
        result["probability_note"] = "Deterministic point-mass control, not the HMM probability of this Viterbi path; no uncertainty is retained."
    result["path_budget"] = request.path_budget
    result["function_budget"] = request.function_budget
    result["unresolved_events"] = [start + i for i, c in enumerate(chords[start : end + 1]) if c.status != "known"]
    return result
