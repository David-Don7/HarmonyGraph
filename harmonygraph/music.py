"""Explicit symbolic theory rules and probabilistic key inference (no source-label leakage)."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from functools import lru_cache
from types import SimpleNamespace
import numpy as np
from scipy.special import logsumexp
from .contracts import AnalysisConfig

NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
MAJOR = [0, 2, 4, 5, 7, 9, 11]
MINOR = [0, 2, 3, 5, 7, 8, 10]
ROMANS = ["I", "II", "III", "IV", "V", "VI", "VII"]
QUALITY_INTERVALS = {
    "major": [0, 4, 7],
    "minor": [0, 3, 7],
    "diminished": [0, 3, 6],
    "augmented": [0, 4, 8],
    "sus2": [0, 2, 7],
    "sus4": [0, 5, 7],
    "power": [0, 7],
    "bass": [0],
}


def pitch(note: str) -> int:
    note = note.replace("♯", "#").replace("♭", "b")
    if not re.fullmatch(r"[A-Ga-g][#b]{0,2}", note):
        raise ValueError(f"Invalid pitch: {note}")
    return (
        {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}[note[0].upper()] + note.count("#") - note.count("b")
    ) % 12


@dataclass
class Chord:
    root: int | None
    quality: str
    intervals: list[int]
    bass: int | None
    status: str = "known"

    @property
    def pcs(self):
        return sorted({(self.root + i) % 12 for i in self.intervals}) if self.root is not None else []

    @property
    def token(self):
        return (
            f"{self.root}:{self.quality}:{','.join(map(str, self.intervals))}/{self.bass}"
            if self.status == "known"
            else self.status
        )

    @property
    def shape(self):
        return f"{self.quality}:{','.join(map(str, self.intervals))}:{(self.bass - self.root) % 12}"

    def data(self):
        return asdict(self)


def parse_chord(label: str, strict=False) -> Chord:
    raw = label.strip().replace("♭", "b").replace("♯", "#").replace("Δ", "maj").replace("ø", "m7b5").replace("°", "dim")
    if raw.upper() in {"N", "NC", "N.C.", "&PAUSE", "NO CHORD"}:
        return Chord(None, "none", [], None, "no_chord")
    aliases = {
        "major seventh": "maj7",
        "minor seventh": "m7",
        "dominant seventh": "7",
        "major": "",
        "minor": "m",
        "diminished": "dim",
        "augmented": "aug",
    }
    for source, target in aliases.items():
        raw = raw.replace(" " + source, target)
    match = re.fullmatch(r"([A-G][#b]{0,2})(.*)", raw)
    try:
        if not match:
            raise ValueError("Expected root A–G")
        root = pitch(match[1])
        rest = match[2].lstrip(":")
        bass = root
        if "/" in rest:
            rest, bass_text = rest.rsplit("/", 1)
            if re.fullmatch(r"[b#]*\d+", bass_text):
                bass = (root + degree_interval(bass_text)) % 12
            else:
                bass = pitch(bass_text)
        rest = (
            rest.replace("hdim7", "m7b5").replace("min", "m").replace("M", "maj").replace("+", "aug").replace("-", "m")
        )
        quality = "major"
        for prefix, q in [
            ("maj", "major"),
            ("dim", "diminished"),
            ("aug", "augmented"),
            ("sus2", "sus2"),
            ("sus4", "sus4"),
            ("sus", "sus4"),
            ("m", "minor"),
        ]:
            if rest.startswith(prefix):
                quality = q
                rest = rest[len(prefix) :]
                break
        if rest == "5":
            quality, rest = "power", ""
        elif rest == "1":
            quality, rest = "bass", ""
        intervals = QUALITY_INTERVALS[quality].copy()
        extension = re.match(r"^(13|11|9|7|6)", rest)
        if extension:
            ext = int(extension[1])
            rest = rest[extension.end() :]
            if ext == 6:
                intervals.append(9)
            else:
                seventh = (
                    11
                    if ("maj" in raw or "M" in raw or "major seventh" in label)
                    else 9
                    if quality == "diminished"
                    else 10
                )
                intervals.append(seventh)
                intervals.extend([v for degree, v in [(9, 2), (11, 5), (13, 9)] if ext >= degree])
        # Harte explicit interval sets replace the shorthand triad only for bare roots.
        explicit = re.fullmatch(r"\(([^)]+)\)", rest)
        if explicit:
            items = explicit[1].split(",")
            if match[2].lstrip(":").startswith("("):
                intervals = [0]
            for item in items:
                omit = item.startswith("*")
                value = degree_interval(item.lstrip("*")) % 12
                if omit:
                    intervals = [v for v in intervals if v != value]
                else:
                    intervals.append(value)
            rest = ""
        while rest:
            alteration = re.match(r"^(add|no|omit)?([b#]?)(2|3|4|5|6|7|9|11|13)", rest)
            if not alteration:
                raise ValueError(f"Unsupported chord suffix: {rest}")
            operation, accidental, degree = alteration.groups()
            natural = degree_interval(degree) % 12
            value = degree_interval(accidental + degree) % 12
            if operation in {"no", "omit"}:
                intervals = [v for v in intervals if v != natural]
            else:
                if accidental and operation != "add":
                    intervals = [v for v in intervals if v != natural]
                intervals.append(value)
            rest = rest[alteration.end() :]
        interval_set = set(intervals)
        if {0, 3, 6}.issubset(interval_set) and 4 not in interval_set:
            quality = "diminished"
        elif {0, 3, 7}.issubset(interval_set) and 4 not in interval_set:
            quality = "minor"
        elif {0, 4, 8}.issubset(interval_set) and 7 not in interval_set:
            quality = "augmented"
        return Chord(root, quality, sorted(interval_set), bass)
    except (ValueError, KeyError) as exc:
        if strict:
            raise ValueError(f"Unsupported chord '{label}': {exc}") from exc
        return Chord(None, "unknown", [], None, "unknown")


def degree_interval(text):
    m = re.fullmatch(r"([b#]*)(\d+)", text)
    if not m or not 1 <= int(m[2]) <= 13:
        raise ValueError(f"Invalid interval {text}")
    return MAJOR[(int(m[2]) - 1) % 7] + 12 * ((int(m[2]) - 1) // 7) + m[1].count("#") - m[1].count("b")


def key_name(index):
    return f"{NAMES[index % 12]} {'minor' if index >= 12 else 'major'}"


def key_index(name):
    parts = name.strip().replace(":", " ").split()
    if len(parts) == 2:
        parts[1] = {"maj": "major", "min": "minor"}.get(parts[1].lower(), parts[1].lower())
    if len(parts) != 2 or parts[1].lower() not in {"major", "minor"}:
        raise ValueError("Key must look like 'C major' or 'A minor'")
    return pitch(parts[0]) + (12 if parts[1].lower() == "minor" else 0)


def tokenize(text):
    return [t.strip() for t in re.split(r"\s*[–—|,]\s*|\s+-\s+|\s+", text.strip()) if t.strip()]


@lru_cache(maxsize=2048)
def roman_features(token):
    m = re.fullmatch(r"([b#]?)([ivIV]+)(maj7|M7|7|6|64|65|43|42|dim|o|ø|aug|\+)?(?:/([b#]?[ivIV]+))?", token)
    if not m or m[2].upper() not in ROMANS:
        raise ValueError(f"Invalid Roman numeral '{token}'; use forms such as I, vi, bVII, V7/V")
    degree = ROMANS.index(m[2].upper())
    root = (MAJOR[degree] + (1 if m[1] == "#" else -1 if m[1] == "b" else 0)) % 12
    quality = "minor" if m[2].islower() else "major"
    suffix = m[3] or ""
    if suffix in {"dim", "o", "ø"}:
        quality = "diminished"
    if suffix in {"aug", "+"}:
        quality = "augmented"
    function = "tonic" if degree in {0, 2, 5} else "predominant" if degree in {1, 3} else "dominant"
    return {
        "degree": degree + 1,
        "root": root,
        "quality": quality,
        "function": function,
        "suffix": suffix,
        "target": m[4],
        "roman": token,
    }


def interpret(chord: Chord, key: int, next_chord: Chord | None = None):
    if chord.status != "known":
        return [
            {
                "roman": "?",
                "function": "unresolved",
                "weight": 1.0,
                "status": chord.status,
                "degree": None,
                "quality": chord.quality,
                "root": None,
            }
        ]
    relative = (chord.root - key % 12) % 12
    # Use major-reference Roman numerals in both modes (minor tonic is i; minor submediant is bVI).
    degree = {0: 0, 1: 1, 2: 1, 3: 2, 4: 2, 5: 3, 6: 3, 7: 4, 8: 5, 9: 5, 10: 6, 11: 6}[relative]
    diff = (relative - MAJOR[degree] + 6) % 12 - 6
    accidental = "b" * -diff if diff < 0 else "#" * diff
    numeral = ROMANS[degree].lower() if chord.quality in {"minor", "diminished"} else ROMANS[degree]
    suffix = "o" if chord.quality == "diminished" else "+" if chord.quality == "augmented" else ""
    if 11 in chord.intervals:
        suffix = "maj7"
    elif 10 in chord.intervals:
        suffix = "7" if chord.quality != "diminished" else "ø"
    scale = MINOR if key >= 12 else MAJOR
    diatonic = all((pc - key % 12) % 12 in scale for pc in chord.pcs)
    opposite = MAJOR if key >= 12 else MINOR
    borrowed = not diatonic and all((pc - key % 12) % 12 in opposite for pc in chord.pcs)
    function = "tonic" if degree in {0, 2, 5} else "predominant" if degree in {1, 3} else "dominant"
    base = {
        "roman": accidental + numeral + suffix,
        "degree": degree + 1,
        "root": relative,
        "quality": chord.quality,
        "function": function,
        "diatonic": diatonic,
        "borrowed": borrowed,
        "secondary": False,
        "inversion": chord.intervals.index((chord.bass - chord.root) % 12)
        if (chord.bass - chord.root) % 12 in chord.intervals
        else None,
        "weight": 1.0,
        "status": "resolved",
        "suffix": suffix,
        "target": None,
    }
    alternatives = [base]
    target_relative = (relative + 5) % 12
    resolves_next = next_chord is not None and next_chord.root == (chord.root + 5) % 12
    if (
        chord.quality == "major"
        and relative != 7
        and target_relative in scale
        and (10 in chord.intervals or (not diatonic and resolves_next))
    ):
        target_degree = min(
            range(7), key=lambda d: min((target_relative - MAJOR[d]) % 12, (MAJOR[d] - target_relative) % 12)
        )
        target = ROMANS[target_degree]
        if target_degree in ({1, 2, 5} if key < 12 else {0, 3, 4}):
            target = target.lower()
        resolved = next_chord is not None and next_chord.root == (chord.root + 5) % 12
        secondary_weight = 0.8 if resolved else 0.35
        base["weight"] = 1 - secondary_weight
        alternatives.append(
            {
                **base,
                "roman": "V" + ("7" if 10 in chord.intervals else "") + "/" + target,
                "function": "dominant",
                "secondary": True,
                "borrowed": False,
                "target": target,
                "weight": secondary_weight,
            }
        )
    return sorted(alternatives, key=lambda x: -x["weight"])


def infer_keys(chords, sections, durations, config: AnalysisConfig):
    n = len(chords)
    if not n:
        return np.empty((0, 24)), []
    evidence = np.zeros((n, 24))
    for i, chord in enumerate(chords):
        if chord.status != "known":
            continue
        for key in range(24):
            scale = MINOR if key >= 12 else MAJOR
            rel = (chord.root - key % 12) % 12
            inside = sum((pc - key % 12) % 12 in scale for pc in chord.pcs) / len(chord.pcs)
            tonic_quality = "minor" if key >= 12 else "major"
            evidence[i, key] = 3 * inside - 1.5 + (1.8 if rel == 0 and chord.quality == tonic_quality else 0)
            evidence[i, key] += 0.8 if rel == 7 and chord.quality == "major" else 0
            evidence[i, key] *= min(max(durations[i] or 1, 0.25), 4)
    if config.local_keys:
        radius = config.window // 2
        emissions = np.array([evidence[max(0, i - radius) : min(n, i + radius + 1)].mean(axis=0) for i in range(n)])
        emissions = emissions + evidence * 0.25
    else:
        emissions = np.tile(evidence.mean(axis=0), (n, 1))
    transitions = []
    for i in range(1, n):
        penalty = config.change_penalty * (0.45 if sections[i] != sections[i - 1] and config.local_keys else 1)
        matrix = np.full((24, 24), -penalty - 3.0 if config.local_keys else -1000.0)
        np.fill_diagonal(matrix, 0)
        transitions.append(matrix - logsumexp(matrix, axis=1)[:, None])
    alpha = np.empty((n, 24))
    alpha[0] = emissions[0] - np.log(24)
    delta = alpha.copy()
    pointers = np.zeros((n, 24), dtype=int)
    for i in range(1, n):
        alpha[i] = emissions[i] + logsumexp(alpha[i - 1][:, None] + transitions[i - 1], axis=0)
        scores = delta[i - 1][:, None] + transitions[i - 1]
        pointers[i] = scores.argmax(axis=0)
        delta[i] = emissions[i] + scores.max(axis=0)
    beta = np.zeros((n, 24))
    for i in range(n - 2, -1, -1):
        beta[i] = logsumexp(transitions[i] + emissions[i + 1][None, :] + beta[i + 1][None, :], axis=1)
    posterior = np.exp(alpha + beta - logsumexp(alpha + beta, axis=1)[:, None])
    path = [int(delta[-1].argmax())]
    for i in range(n - 1, 0, -1):
        path.append(int(pointers[i, path[-1]]))
    return posterior, path[::-1]


def _alignment_impl(query, target, config, functional=True):
    """Global weighted alignment of a query against one bounded candidate passage."""
    n, m = len(query), len(target)
    costs = np.zeros((n + 1, m + 1))
    ops = {}
    costs[:, 0] = np.arange(n + 1) * config.deletion
    costs[0, :] = np.arange(m + 1) * config.insertion

    def substitution(a, b):
        if a == b:
            return 0.0
        if not config.theory_costs:
            return 1.0
        if not functional:
            return config.substitution
        try:
            af, bf = roman_features(a), roman_features(b)
        except ValueError:
            return 1.0
        degree = 0 if not config.functions or (af["root"] == bf["root"] and af["target"] == bf["target"]) else 0.55
        quality = 0 if not config.qualities or af["quality"] == bf["quality"] else 0.2
        extension = 0 if not config.qualities or af["suffix"] == bf["suffix"] else 0.1
        function = 0 if not config.functions or af["function"] == bf["function"] else 0.15
        return config.substitution * (degree + quality + extension + function)

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            sc = substitution(query[i - 1], target[j - 1])
            repeated = j > 1 and target[j - 1] == target[j - 2]
            insertion = config.repetition if repeated and config.theory_costs else config.insertion
            options = [
                (costs[i - 1, j - 1] + sc, "match" if sc == 0 else "substitute", sc),
                (costs[i - 1, j] + config.deletion, "delete", config.deletion),
                (costs[i, j - 1] + insertion, "repeat" if repeated else "insert", insertion),
            ]
            value, op, cost = min(options, key=lambda x: x[0])
            costs[i, j] = value
            ops[i, j] = (op, cost)
    trace = []
    i, j = n, m
    while i or j:
        op, cost = ops[i, j] if i and j else ("delete", config.deletion) if i else ("insert", config.insertion)
        trace.append(
            {
                "operation": op,
                "query_index": i - 1 if op in {"match", "substitute", "delete"} else None,
                "target_index": j - 1 if op != "delete" else None,
                "cost": float(cost),
            }
        )
        if op in {"match", "substitute"}:
            i, j = i - 1, j - 1
        elif op == "delete":
            i -= 1
        else:
            j -= 1
    return max(0.0, 1 - float(costs[n, m]) / max(n, m, 1)), trace[::-1]


_ALIGNMENT_FIELDS = ("insertion", "deletion", "substitution", "repetition", "theory_costs", "qualities", "functions")


@lru_cache(maxsize=32768)
def _cached_alignment(query, target, settings, functional):
    config = SimpleNamespace(**dict(zip(_ALIGNMENT_FIELDS, settings)))
    score, trace = _alignment_impl(query, target, config, functional)
    return score, tuple((op["operation"], op["query_index"], op["target_index"], op["cost"]) for op in trace)


def alignment(query, target, config, functional=True):
    settings = tuple(getattr(config, name) for name in _ALIGNMENT_FIELDS)
    score, trace = _cached_alignment(tuple(query), tuple(target), settings, functional)
    return score, [{"operation": op, "query_index": qi, "target_index": ti, "cost": cost} for op, qi, ti, cost in trace]
