import numpy as np
import pytest
from harmonygraph.contracts import AnalysisConfig
from harmonygraph.music import alignment, infer_keys, interpret, parse_chord, roman_features


@pytest.mark.parametrize("label", ["Cmaj7", "C:M7", "C major seventh", "C:maj7"])
def test_major_seventh_aliases(label):
    chord = parse_chord(label, strict=True)
    assert chord.pcs == [0, 4, 7, 11]
    assert chord.quality == "major"


@pytest.mark.parametrize(
    "label,pcs,bass",
    [
        ("C/E", [0, 4, 7], 4),
        ("C:maj/3", [0, 4, 7], 4),
        ("C7b9", [0, 1, 4, 7, 10], 0),
        ("Bm7b5", [2, 5, 9, 11], 11),
        ("Csus4", [0, 5, 7], 0),
        ("Cdim7", [0, 3, 6, 9], 0),
        ("C:(1,b3,5,b7)", [0, 3, 7, 10], 0),
    ],
)
def test_chord_content(label, pcs, bass):
    chord = parse_chord(label, strict=True)
    assert chord.pcs == pcs
    assert chord.bass == bass


def test_unknown_not_no_chord():
    assert parse_chord("nonsense").status == "unknown"
    assert parse_chord("N").status == "no_chord"
    with pytest.raises(ValueError):
        parse_chord("Cgarbage", strict=True)


def test_secondary_and_borrowed():
    readings = interpret(parse_chord("D7"), 0, parse_chord("G"))
    assert readings[0]["roman"] == "V7/V"
    assert sum(r["weight"] for r in readings) == pytest.approx(1)
    assert interpret(parse_chord("Ab"), 0)[0]["roman"] == "bVI"
    assert interpret(parse_chord("Ab"), 0)[0]["borrowed"]
    assert interpret(parse_chord("C"), 0)[0]["weight"] == 1


def test_inference_probability_and_modulation():
    labels = ["C", "F", "G7", "C"] * 5 + ["Am", "Dm", "E7", "Am"] * 7
    posterior, path = infer_keys([parse_chord(c) for c in labels], [0] * 20 + [1] * 28, [1] * 48, AnalysisConfig())
    assert np.allclose(posterior.sum(axis=1), 1)
    assert np.isfinite(posterior).all()
    assert path[3] == 0
    assert path[-3] == 21
    assert np.count_nonzero(posterior[0]) == 24


def test_global_key_is_constant():
    chords = [parse_chord(c) for c in ["C", "G7", "C", "Am", "E7", "Am"] * 4]
    _, path = infer_keys(chords, [0] * 12 + [1] * 12, [1] * 24, AnalysisConfig(local_keys=False))
    assert len(set(path)) == 1


def test_theory_alignment_prefers_small_changes():
    cfg = AnalysisConfig()
    close, trace = alignment(["I", "V", "vi", "IV"], ["I", "I", "V7", "vi", "IV"], cfg)
    far, _ = alignment(["I", "V", "vi", "IV"], ["bII", "iii", "bVI", "vii"], cfg)
    assert close > far
    assert any(t["operation"] == "repeat" for t in trace)
    assert 0 <= close <= 1


def test_invalid_roman_rejected():
    with pytest.raises(ValueError):
        roman_features("VIII")
