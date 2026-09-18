"""Reference-driven harmonic evaluation; missing annotations remain explicitly unavailable."""

import numpy as np
from sqlalchemy import select
from .db import ChordEvent, FunctionalInterpretation, HarmonicRelation, SongAnalysis, SourceAnnotation
from .metrics import boundary_metrics, uncertainty_metrics
from .music import key_index


def harmonic_evaluation(session, analysis_id, song_ids, top_k):
    probabilities, references, roman_hits = [], [], []
    boundary_scores = {"key_boundaries": [], "modulation_boundaries": [], "cadence_boundaries": []}
    for song_id in song_ids:
        source = session.scalar(select(SourceAnnotation).where(SourceAnnotation.song_id == song_id))
        analysis = session.get(SongAnalysis, (analysis_id, song_id))
        if not source or not analysis:
            continue
        annotations = source.data.get("annotations", {})
        events = list(
            session.scalars(select(ChordEvent).where(ChordEvent.song_id == song_id).order_by(ChordEvent.ordinal))
        )
        reference_keys = {}
        for position, label in annotations.get("event_keys", {}).items():
            position = int(position)
            if not 0 <= position < len(events):
                raise ValueError("Reference key position is outside the song")
            reference_keys[position] = key_index(label) if isinstance(label, str) else int(label)
        if not reference_keys and "expected_opening_key" in annotations:
            reference_keys[0] = annotations["expected_opening_key"]
        if not reference_keys and annotations.get("keys"):
            for event in events:
                if event.onset is None or event.timing_unit != "seconds":
                    continue
                for start, end, label in annotations["keys"]:
                    if start <= event.onset < end:
                        try:
                            reference_keys[event.ordinal] = key_index(label)
                        except ValueError:
                            pass
                        break
        for position, label in reference_keys.items():
            if not 0 <= label < 24:
                raise ValueError("Reference keys must be one of the 24 major/minor states")
            probabilities.append(analysis.posterior[position])
            references.append(label)
        reference_romans = annotations.get("event_romans", {})
        if reference_romans:
            predicted = {}
            interpretations = session.scalars(
                select(FunctionalInterpretation)
                .join(ChordEvent, FunctionalInterpretation.event_id == ChordEvent.id)
                .where(ChordEvent.song_id == song_id, FunctionalInterpretation.analysis_id == analysis_id)
                .order_by(FunctionalInterpretation.confidence.desc())
            )
            event_positions = {event.id: event.ordinal for event in events}
            for interpretation in interpretations:
                predicted.setdefault(event_positions[interpretation.event_id], interpretation.roman)
            for position, accepted in reference_romans.items():
                if isinstance(accepted, str):
                    accepted = [accepted]
                roman_hits.append(predicted.get(int(position)) in accepted)
        relations = list(
            session.scalars(
                select(HarmonicRelation).where(
                    HarmonicRelation.song_id == song_id, HarmonicRelation.analysis_id == analysis_id
                )
            )
        )
        for metric, accumulated in boundary_scores.items():
            if metric not in annotations:
                continue
            if metric == "key_boundaries":
                predicted = [i for i in range(1, len(analysis.path)) if analysis.path[i] != analysis.path[i - 1]]
            else:
                kinds = (
                    {"modulation", "relative_minor_modulation"}
                    if metric == "modulation_boundaries"
                    else {"dominant_resolution", "plagal_motion", "half_cadence"}
                )
                predicted = [r.end for r in relations if r.kind in kinds]
            accumulated.append(boundary_metrics(predicted, annotations[metric], tolerance=1))
    report = {
        "uncertainty": uncertainty_metrics(probabilities, references, top_k),
        "reference_key_events": len(references),
        "roman_accuracy": {"available": True, "accuracy": float(np.mean(roman_hits)), "events": len(roman_hits)}
        if roman_hits
        else {"available": False, "reason": "No aligned event_romans references supplied"},
    }
    for name, values in boundary_scores.items():
        report[name] = (
            {
                "available": True,
                "songs": len(values),
                "tolerance_events": 1,
                "averaging": "macro by annotated song",
                **{metric: float(np.mean([v[metric] for v in values])) for metric in ("precision", "recall", "f1")},
            }
            if values
            else {"available": False, "reason": f"No explicit {name} references supplied"}
        )
    return report
