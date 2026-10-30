"""Research v2: query-independent passage paths conditioned on full chart context.

Outside-passage states are marginalized by forward/backward inference. Retained
paths are mutually exclusive assignments of every key/function inside the passage.
Beam selection is approximate; ORIGINAL probabilities are never renormalized.
"""

from __future__ import annotations

from collections import OrderedDict
from functools import lru_cache
from heapq import nsmallest
from threading import RLock

import numpy as np
from scipy.special import logsumexp

from .contracts import fingerprint
from .music import Chord, alignment, infer_keys, interpret, key_name

VERSION = "context-path-expectation-v1"

# Cache model inputs, never query results or candidate lists. A changed chart,
# duration, section, or inference setting therefore cannot reuse stale messages.
_contexts = OrderedDict()
_context_lock = RLock()
_context_bytes = 0
_CONTEXT_BYTES = 32 * 1024 * 1024


class PreparedContext(tuple):
    """Tuple-compatible HMM messages with reusable backward conditionals."""

    def __new__(cls, messages):
        posterior, path, emissions, transitions, beta = messages
        for array in (posterior, emissions, beta, *transitions):
            array.flags.writeable = False
        value = super().__new__(cls, (posterior, tuple(path), emissions, tuple(transitions), beta))
        value.conditionals = {}
        return value

    def conditional(self, t):
        if t not in self.conditionals:
            _, _, emissions, transitions, beta = self
            logp = transitions[t - 1] + emissions[t][None, :] + beta[t][None, :]
            conditional = np.exp(logp - logsumexp(logp, axis=1)[:, None])
            conditional.flags.writeable = False
            self.conditionals[t] = conditional
        return self.conditionals[t]


def _chord_signature(chord):
    return chord.root, chord.quality, tuple(chord.intervals), chord.bass, chord.status


@lru_cache(maxsize=8192)
def _function_options(chord, key, following):
    def restore(signature):
        return Chord(*signature) if signature is not None else None

    return tuple((option["roman"], option["weight"]) for option in interpret(restore(chord), key, restore(following)))


def context_messages(chords, events, config):
    global _context_bytes
    key = (
        tuple(_chord_signature(c) for c in chords),
        tuple((e.section_id, e.duration) for e in events),
        config.window, config.change_penalty, config.local_keys,
    )
    with _context_lock:
        if key in _contexts:
            _contexts.move_to_end(key)
            return _contexts[key][0]
    value = PreparedContext(infer_keys(
        chords, [e.section_id for e in events], [e.duration for e in events], config, return_messages=True
    ))
    # Reserve space for every lazy 24x24 conditional, inference arrays and keys.
    # Oversized charts still work; they simply bypass the process cache.
    size = len(chords) * 8192
    if size <= _CONTEXT_BYTES:
        with _context_lock:
            if key not in _contexts:
                _contexts[key] = value, size
                _context_bytes += size
            while len(_contexts) > 128 or _context_bytes > _CONTEXT_BYTES:
                _, (_, evicted_size) = _contexts.popitem(last=False)
                _context_bytes -= evicted_size
    return value


def key_paths(messages, start, end, budget):
    posterior, _, emissions, transitions, beta = messages
    beam = [((k,), float(posterior[start, k])) for k in range(24)]
    beam = sorted(beam, key=lambda item: (-item[1], item[0]))[:budget]
    for t in range(start + 1, end + 1):
        if isinstance(messages, PreparedContext):
            conditional = messages.conditional(t)
        else:
            logp = transitions[t - 1] + emissions[t][None, :] + beta[t][None, :]
            conditional = np.exp(logp - logsumexp(logp, axis=1)[:, None])
        expanded = (
            (path + (k,), probability * float(conditional[path[-1], k]))
            for path, probability in beam
            for k in range(24)
        )
        # Select only the required prefixes, preserving the exact probability
        # and lexicographic tie order of a full sort.
        beam = nsmallest(budget, expanded, key=lambda item: (-item[1], item[0]))
    return beam


def joint_paths(chords, messages, start, end, key_budget=64, function_budget=16, hard=False):
    keys = ([(tuple(messages[1][start : end + 1]), 1.0)] if hard
            else key_paths(messages, start, end, key_budget))
    signatures = [_chord_signature(c) for c in chords[start : min(end + 2, len(chords))]]
    retained = []
    for key_sequence, probability in keys:
        beam = [((), 1.0)]
        for offset, key in enumerate(key_sequence):
            t = start + offset
            options = _function_options(
                signatures[offset], key, signatures[offset + 1] if t + 1 < len(chords) else None
            )
            if hard:
                options = [(options[0][0], 1.0)]
            expanded = [
                (sequence + (roman,), weight * option_weight)
                for sequence, weight in beam
                for roman, option_weight in options
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
