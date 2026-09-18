"""Original, synthetic fixtures; no external corpus is bundled."""

import json
from pathlib import Path
from sqlalchemy import select
from .contracts import SearchRequest, fingerprint
from .db import Benchmark, BenchmarkQuery, Song
from .music import NAMES

FAMILIES = [
    ("pop_cycle", [(0, ""), (7, ""), (9, "m"), (5, "")], "I V vi IV"),
    ("jazz_resolution", [(2, "m7"), (7, "7"), (0, "maj7")], "ii7 V7 Imaj7"),
    ("secondary_dominant", [(2, "7"), (7, ""), (0, "")], "V7/V V I"),
    ("borrowed_harmony", [(8, ""), (10, ""), (0, "")], "bVI bVII I"),
    ("plagal", [(5, ""), (0, "")], "IV I"),
    ("chorus_ending", [(2, "m"), (5, ""), (7, "7"), (0, "")], "V7 I"),
    ("repetition", [(0, ""), (0, ""), (7, ""), (9, "m"), (5, "")], "I V vi IV"),
    ("quality_variant", [(0, "maj7"), (7, "7"), (9, "m7"), (5, "maj7")], "I V vi IV"),
    ("relative_ambiguity", [(9, "m"), (5, ""), (0, ""), (7, "")], "vi IV I V"),
    ("modulation", [(0, ""), (5, ""), (7, "7"), (0, "")], "I IV V7 I"),
]


def generate(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for family_index, (family, pattern, _) in enumerate(FAMILIES):
            for transpose in range(12):

                def events(seq):
                    return [
                        {"label": NAMES[(root + transpose) % 12] + quality, "duration": 1, "timing_unit": "beats"}
                        for root, quality in seq
                    ]

                grounding = [(0, ""), (5, ""), (7, "7"), (0, "")] * 2
                sections = [
                    {"label": "Verse 1", "events": events(grounding)},
                    {"label": "Chorus 1", "events": events(pattern)},
                    {"label": "Bridge", "events": events([(2, "m"), (7, "7"), (0, "")])},
                    {"label": "Chorus 2", "events": events(pattern)},
                ]
                if family == "modulation":
                    sections[-2] = {"label": "Bridge", "events": events([(9, "m"), (2, "m"), (4, "7"), (9, "m")] * 4)}
                    sections[-1]["events"] = events([(9, "m"), (2, "m"), (4, "7"), (9, "m")] * 2)
                json.dump(
                    {
                        "source_id": f"demo-{family}-{transpose}",
                        "title": f"{family.replace('_', ' ').title()} · {NAMES[transpose]}",
                        "artist": f"Synthetic Ensemble {family_index + 1:02}",
                        "genres": ["synthetic", ["pop", "jazz", "rock"][family_index % 3]],
                        "year": 2000 + family_index * 2,
                        "duplicate_group": "demo-pop-cycle" if family_index in {0, 6, 7} else f"demo-{family}",
                        "sections": sections,
                        "synthetic": True,
                        "annotations": {
                            "expected_opening_key": transpose,
                            "family": family,
                            "notice": "Constructed fixture, not expert annotation",
                        },
                    },
                    handle,
                )
                handle.write("\n")
    return str(path)


def seed_benchmark(session):
    name = "Synthetic harmonic retrieval v2"
    existing = session.scalar(select(Benchmark).where(Benchmark.name == name))
    if existing:
        return existing.id
    songs = list(session.scalars(select(Song).where(Song.synthetic.is_(True)).order_by(Song.source_id)))
    benchmark = Benchmark(id=fingerprint([name, [s.id for s in songs]]), name=name, synthetic=True)
    session.add(benchmark)
    session.flush()

    def family_of(song):
        return song.source_id.removeprefix("demo-").rsplit("-", 1)[0]

    def shift_of(song):
        return int(song.source_id.rsplit("-", 1)[1])

    pop_families = {"pop_cycle", "repetition", "quality_variant"}
    for song in songs:
        family = family_of(song)
        index = next(i for i, f in enumerate(FAMILIES) if f[0] == family)
        shift = shift_of(song)
        mode = "fuzzy" if family in {"repetition", "quality_variant"} else "functional"
        request = SearchRequest(progression=FAMILIES[index][2], mode=mode, section="chorus", limit=100)
        category = family
        if family == "pop_cycle" and shift % 3 in {0, 1}:
            request.mode = "literal" if shift % 3 == 0 else "transposed"
            request.progression = " ".join(NAMES[(r + shift) % 12] + q for r, q in FAMILIES[index][1])
            category = "exact" if request.mode == "literal" else "transposed"
        if family == "chorus_ending":
            request.boundary = "end"
        if family == "repetition" and shift % 2:
            request.every_chorus = True
            category = "repeated_every_chorus"
        if family == "quality_variant" and shift % 3 == 0:
            request.progression = "I vi IV"
            category = "omitted_chord"
        if family == "modulation":
            request.pattern, request.section = "relative_minor_modulation", None
        relevant = {}
        for other in songs:
            other_family = family_of(other)
            other_index = next(i for i, f in enumerate(FAMILIES) if f[0] == other_family)
            size = len(FAMILIES[other_index][1])
            starts = [8, 8 + size + 3]
            if family == "modulation":
                if other_family == "modulation":
                    # The fixture intentionally begins its minor bridge at event 12.
                    # One-event annotation tolerance is represented explicitly as accepted windows.
                    for boundary in (11, 12, 13):
                        relevant[f"{other.id}:{boundary - 1}:{boundary}"] = 2
                continue
            same_shape = other_family == family
            pop_equivalent = family in pop_families and other_family in pop_families
            if request.mode == "literal" and shift_of(other) != shift:
                same_shape = pop_equivalent = False
            if same_shape or pop_equivalent:
                for start in starts:
                    end = start + size - 1
                    if family == "chorus_ending":
                        start = end - 1
                    if (
                        request.mode in {"literal", "transposed", "functional"}
                        and other_family == "quality_variant"
                        and family != "quality_variant"
                    ):
                        relevant[f"{other.id}:{start}:{end}"] = 1
                    else:
                        relevant[f"{other.id}:{start}:{end}"] = 2
                    if other_family == "repetition" and family in pop_families:
                        relevant[f"{other.id}:{start + 1}:{end}"] = 2
                    if request.mode == "fuzzy" and family in pop_families:
                        # Constructed omission variants have partial relevance, distinct from negatives.
                        relevant.setdefault(f"{other.id}:{max(start, end - 2)}:{end}", 1)
            elif other_family not in {"modulation", "chorus_ending"}:
                for start in starts:
                    relevant[f"{other.id}:{start}:{start + size - 1}"] = 0
        session.add(
            BenchmarkQuery(
                id=fingerprint([benchmark.id, song.id]),
                benchmark_id=benchmark.id,
                category=category,
                request=request.model_dump(),
                source_song_id=song.id,
                synthetic_judgments=relevant,
            )
        )
    session.commit()
    return benchmark.id
