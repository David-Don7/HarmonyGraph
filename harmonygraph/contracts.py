from __future__ import annotations

import hashlib
import json
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


def fingerprint(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EventInput(StrictModel):
    label: str
    onset: float | None = None
    duration: float | None = Field(default=None, ge=0)
    timing_unit: Literal["seconds", "beats", "unknown"] = "unknown"


class SectionInput(StrictModel):
    label: str = "unknown"
    events: list[EventInput] = Field(min_length=1)


class SongInput(StrictModel):
    source_id: str
    title: str | None = None
    artist: str | None = None
    genres: list[str] = []
    year: int | None = None
    duplicate_group: str | None = None
    sections: list[SectionInput] = Field(min_length=1)
    annotations: dict = {}
    synthetic: bool = False


class AnalysisConfig(StrictModel):
    algorithm: str = "hmm-functional-v4"
    window: int = Field(default=8, ge=4, le=16)
    change_penalty: float = Field(default=1.8, ge=0.1, le=3)
    top_k: int = Field(default=3, ge=1, le=5)
    confidence_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    functional_weight: float = Field(default=0.60, ge=0)
    chord_weight: float = Field(default=0.25, ge=0)
    section_weight: float = Field(default=0.10, ge=0)
    boundary_weight: float = Field(default=0.05, ge=0)
    insertion: float = Field(default=0.6, gt=0, le=1)
    deletion: float = Field(default=0.6, gt=0, le=1)
    substitution: float = Field(default=0.8, ge=0, le=1)
    repetition: float = Field(default=0.15, gt=0, le=1)
    candidate_limit: int = Field(default=500, ge=100, le=5000)
    seed: int = 42
    uncertainty: bool = True
    local_keys: bool = True
    functions: bool = True
    sections: bool = True
    boundaries: bool = True
    theory_costs: bool = True
    qualities: bool = True

    @model_validator(mode="after")
    def positive_weights(self):
        if self.functional_weight + self.chord_weight <= 0:
            raise ValueError("At least one harmonic score weight must be positive")
        return self


class SearchRequest(StrictModel):
    progression: str = ""
    mode: Literal["literal", "transposed", "functional", "fuzzy"] = "functional"
    ranking: Literal["legacy_mixture", "path_expectation", "hard_path", "max_path", "equal_paths", "shuffled_paths"] = (
        "legacy_mixture"
    )
    path_budget: int = Field(default=64, ge=1, le=4096)
    function_budget: int = Field(default=16, ge=1, le=256)
    match_threshold: float = Field(default=0.8, ge=0, le=1)
    pattern: Literal["progression", "relative_minor_modulation"] = "progression"
    section: str | None = None
    preferred_section: str | None = None
    boundary: Literal["start", "end", "interior", "adjacent"] | None = None
    preferred_boundary: Literal["start", "end"] | None = None
    boundary_distance: int = Field(default=0, ge=0, le=16)
    genre: str | None = None
    year_from: int | None = None
    year_to: int | None = None
    key: str | None = None
    cross_sections: bool = False
    every_chorus: bool = False
    required_features: list[str] = []
    optional_features: list[str] = []
    tolerance: float = Field(default=0.45, ge=0, le=1)
    limit: int = Field(default=20, ge=1, le=100)
    analysis_id: str | None = None
    dataset_ids: list[str] = []
    song_ids: list[str] = []
    catalog_snapshot: str | None = None

    @model_validator(mode="after")
    def validate_query(self):
        if self.pattern == "progression" and not self.progression.strip():
            raise ValueError("Enter a chord or Roman-numeral progression")
        if self.year_from and self.year_to and self.year_from > self.year_to:
            raise ValueError("The start year must precede the end year")
        if self.ranking != "legacy_mixture":
            from .music import tokenize, roman_features

            tokens = tokenize(self.progression)
            if self.mode not in {"functional", "fuzzy"} or self.pattern != "progression" or not 2 <= len(tokens) <= 8:
                raise ValueError("Research v2 requires an explicit functional query of 2–8 Roman numerals")
            for token in tokens:
                roman_features(token)
        return self


class SearchResult(StrictModel):
    passage_id: str
    song_id: str
    title: str
    artist: str | None
    section: str
    start: int
    end: int
    labels: list[str]
    score: float
    key_hypotheses: list[dict]
    retained_mass: float
    interpretation: list[str]
    alignment: list[dict]
    components: dict
    evidence: dict
    explanation: str
    analysis_id: str


class SearchResponse(StrictModel):
    results: list[SearchResult]
    analysis_id: str
    candidate_count: int
    candidate_limit_reached: bool
    timings: dict[str, float]


class JudgmentInput(StrictModel):
    query_id: str
    passage_id: str
    annotator_id: str
    relevance: int | None = Field(default=None, ge=0, le=2)
    status: Literal["judged", "insufficient_context", "unsupported", "unresolved"] = "judged"
    supported_interpretations: list[str] = []
    section_correct: bool | None = None
    evidence_basis: Literal["chord-only", "audio-assisted"] = "chord-only"
    adjudication_sources: list[str] = []

    @model_validator(mode="after")
    def judgment_status(self):
        if (self.status == "judged") != (self.relevance is not None):
            raise ValueError("Provide a relevance grade only for judged cases; unresolved cases must have a null grade")
        return self

    correctness: int | None = Field(default=None, ge=1, le=5)
    clarity: int | None = Field(default=None, ge=1, le=5)
    usefulness: int | None = Field(default=None, ge=1, le=5)
    notes: str = ""
    adjudicated: bool = False


class JobInput(StrictModel):
    kind: Literal[
        "demo",
        "import",
        "analyze",
        "evaluate",
        "optimize",
        "export",
        "catalog_download",
        "catalog_import",
        "catalog_metadata",
        "catalog_analyze",
        "research_v2_compare",
    ]
    parameters: dict = {}


class JobResponse(StrictModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    kind: str
    status: str
    progress: float
    parameters: dict
    result: dict
    error: str | None
    created_at: str
    updated_at: str
