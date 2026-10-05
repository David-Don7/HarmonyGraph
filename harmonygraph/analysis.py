from collections import defaultdict
import time
import numpy as np
from sqlalchemy import select, update
from .contracts import AnalysisConfig, fingerprint
from .db import (
    AnalysisRun,
    ChordDefinition,
    ChordEvent,
    Dataset,
    FunctionalInterpretation,
    HarmonicRelation,
    LocalKeyHypothesis,
    ModelConfiguration,
    PatternIndex,
    Section,
    Song,
    SongAnalysis,
    uid,
)
from .music import Chord, infer_keys, interpret, roman_features


def corpus_hash(session, song_ids=None):
    query = select(Song.id, Song.content_hash, Dataset.fingerprint).join(Dataset).order_by(Song.id)
    if song_ids is not None:
        query = query.where(Song.id.in_(song_ids))
    return fingerprint(list(session.execute(query).tuples()))


def save_config(session, config, name="Manual defaults"):
    config_id = fingerprint(config.model_dump())
    if not session.get(ModelConfiguration, config_id):
        session.add(ModelConfiguration(id=config_id, name=name, parameters=config.model_dump()))
        session.commit()
    return config_id


def analyze(session, config=None, activate=True, progress=lambda p: None, song_ids=None):
    started = time.perf_counter()
    config = config or AnalysisConfig()
    config_id = save_config(session, config)
    corpus = corpus_hash(session, song_ids)
    cached = session.scalar(
        select(AnalysisRun).where(
            AnalysisRun.configuration_id == config_id, AnalysisRun.corpus_hash == corpus, AnalysisRun.status == "ready"
        )
    )
    if cached:
        if activate:
            session.execute(update(AnalysisRun).values(active=False))
            cached.active = True
            session.commit()
        return cached.id
    run = AnalysisRun(configuration_id=config_id, corpus_hash=corpus)
    session.add(run)
    session.commit()
    ids = sorted(song_ids) if song_ids is not None else list(session.scalars(select(Song.id).order_by(Song.id)))
    try:
        for number, song_id in enumerate(ids):
            process_song(session, song_id, run.id, config)
            session.commit()
            progress((number + 1) / max(len(ids), 1))
        run.status = "ready"
        run.report = {
            "songs": len(ids),
            "algorithm": config.algorithm,
            "index_version": 1,
            "analysis_and_index_seconds": time.perf_counter() - started,
        }
        if activate:
            session.execute(update(AnalysisRun).values(active=False))
            run.active = True
        session.commit()
        return run.id
    except BaseException as error:
        session.rollback()
        run = session.get(AnalysisRun, run.id)
        run.status = "failed"
        run.report = {"error": str(error)}
        session.commit()
        raise


def process_song(session, song_id, run_id, config):
    rows = list(
        session.execute(
            select(ChordEvent, ChordDefinition)
            .join(ChordDefinition)
            .where(ChordEvent.song_id == song_id)
            .order_by(ChordEvent.ordinal)
        )
    )
    events, chords = [r[0] for r in rows], [Chord(**r[1].canonical) for r in rows]
    posterior, path = infer_keys(chords, [e.section_id for e in events], [e.duration for e in events], config)
    session.add(SongAnalysis(analysis_id=run_id, song_id=song_id, posterior=posterior.tolist(), path=path))
    functions = defaultdict(list)
    hypothesis_rows, interpretation_rows = [], []
    for i, (event, chord) in enumerate(zip(events, chords)):
        keys = np.argsort(posterior[i])[::-1][: config.top_k if config.uncertainty else 1]
        for key in keys:
            confidence = float(posterior[i, key])
            hypothesis = LocalKeyHypothesis(
                id=uid(), analysis_id=run_id, event_id=event.id, key_index=int(key), confidence=confidence
            )
            hypothesis_rows.append({c.name: getattr(hypothesis, c.name) for c in hypothesis.__table__.columns})
            for alternative in interpret(chord, int(key), chords[i + 1] if i + 1 < len(chords) else None):
                interpretation_rows.append(
                    dict(
                        id=uid(),
                        hypothesis_id=hypothesis.id,
                        event_id=event.id,
                        analysis_id=run_id,
                        key_index=int(key),
                        roman=alternative["roman"],
                        confidence=confidence * alternative["weight"],
                        data=alternative,
                    )
                )
                functions[i].append(alternative["roman"])
                for feature in ("borrowed", "secondary"):
                    if alternative.get(feature):
                        session.add(
                            HarmonicRelation(
                                analysis_id=run_id,
                                song_id=song_id,
                                kind=feature,
                                start=i,
                                end=min(i + 1, len(events) - 1),
                                confidence=confidence * alternative["weight"],
                                evidence={
                                    "event_ids": [event.id],
                                    "key": int(key),
                                    "interpretation": alternative["roman"],
                                },
                            )
                        )
        if i and path[i] != path[i - 1]:
            kind = (
                "relative_minor_modulation"
                if path[i - 1] < 12 and path[i] == (path[i - 1] + 9) % 12 + 12
                else "modulation"
            )
            confidence = min(float(posterior[i, path[i]]), float(posterior[i - 1, path[i - 1]]))
            if confidence >= config.confidence_threshold:
                session.add(
                    HarmonicRelation(
                        analysis_id=run_id,
                        song_id=song_id,
                        kind=kind,
                        start=i - 1,
                        end=i,
                        confidence=confidence,
                        evidence={
                            "event_ids": [events[i - 1].id, event.id],
                            "from_key": path[i - 1],
                            "to_key": path[i],
                        },
                    )
                )
        if i and chord.root is not None and chords[i - 1].root is not None:
            previous = chords[i - 1]
            kind = (
                "dominant_resolution"
                if (previous.root - chord.root) % 12 == 7 and previous.quality == "major"
                else "plagal_motion"
                if (previous.root - chord.root) % 12 == 5
                else None
            )
            if kind:
                confidence = float(posterior[i, path[i]])
                session.add(
                    HarmonicRelation(
                        analysis_id=run_id,
                        song_id=song_id,
                        kind=kind,
                        start=i - 1,
                        end=i,
                        confidence=confidence,
                        evidence={"event_ids": [events[i - 1].id, event.id], "label": "harmonic cadence candidate"},
                    )
                )
    # Three or more roots descending by fifth, led by major-quality dominants.
    # Keep this as an inspectable harmonic candidate, not a categorical cadence claim.
    chain_start = None
    for i in range(len(chords)):
        resolves = (
            i + 1 < len(chords)
            and chords[i].status == chords[i + 1].status == "known"
            and chords[i].quality == "major"
            and (chords[i].root - chords[i + 1].root) % 12 == 7
        )
        if resolves and chain_start is None:
            chain_start = i
        if not resolves and chain_start is not None:
            if i - chain_start >= 2:
                session.add(
                    HarmonicRelation(
                        analysis_id=run_id,
                        song_id=song_id,
                        kind="secondary_dominant_chain",
                        start=chain_start,
                        end=i,
                        confidence=min(float(posterior[j, path[j]]) for j in range(chain_start, i + 1)),
                        evidence={
                            "event_ids": [e.id for e in events[chain_start : i + 1]],
                            "roots": [c.root for c in chords[chain_start : i + 1]],
                            "label": "secondary-dominant chain candidate",
                            "rule": "at least two consecutive major-quality descending-fifth resolutions",
                        },
                    )
                )
            chain_start = None
    if hypothesis_rows:
        session.execute(LocalKeyHypothesis.__table__.insert(), hypothesis_rows)
        session.execute(FunctionalInterpretation.__table__.insert(), interpretation_rows)
    sections = list(session.scalars(select(Section).where(Section.song_id == song_id)))
    for section in sections:
        last = section.end
        best = interpret(chords[last], path[last])[0]
        if best["roman"] in {"V", "V7"}:
            session.add(
                HarmonicRelation(
                    analysis_id=run_id,
                    song_id=song_id,
                    kind="half_cadence",
                    start=last,
                    end=last,
                    confidence=float(posterior[last, path[last]]),
                    evidence={"event_ids": [events[last].id], "label": "harmonic cadence candidate"},
                )
            )
    index_rows = []

    def add(mode, token, pos):
        index_rows.append(
            {
                "analysis_id": run_id,
                "song_id": song_id,
                "section_id": events[pos].section_id,
                "mode": mode,
                "token": token,
                "position": pos,
            }
        )

    for i, chord in enumerate(chords):
        if chord.status == "known":
            add("literal", chord.token, i)
            add("shape", chord.shape, i)
            add("quality", chord.quality, i)
            if i + 1 < len(chords) and chords[i + 1].status == "known":
                add("transposed", f"{(chords[i + 1].root - chord.root) % 12}:{chord.shape}:{chords[i + 1].shape}", i)
        for token in set(functions[i]):
            if token != "?":
                add("functional", token, i)
                try:
                    add("degree", str(roman_features(token)["root"]), i)
                except ValueError:
                    pass
        for length in (2, 3):
            if i + length <= len(chords):
                add("literal_ngram", "|".join(c.token for c in chords[i : i + length]), i)
                add(
                    "functional_ngram",
                    "|".join(
                        interpret(chords[j], path[j], chords[j + 1] if j + 1 < len(chords) else None)[0]["roman"]
                        for j in range(i, i + length)
                    ),
                    i,
                )
    if index_rows:
        session.execute(PatternIndex.__table__.insert(), index_rows)
    session.flush()
