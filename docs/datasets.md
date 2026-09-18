# Dataset adapters and reference annotations

No copyrighted song corpus or audio is bundled. `data/demo/songs.jsonl` contains original synthetic fixtures and is available under CC0-1.0. Preserve source licensing and citation requirements for external imports; a software repository license is not necessarily the dataset license.

## Canonical JSONL

One validated song per line. Missing title, artist, year, duration, and key remain unknown.

```json
{"source_id":"example-1","title":"An original example","artist":"Example researcher","genres":["example"],"year":2026,"duplicate_group":"composition-1","sections":[{"label":"Chorus 1","events":[{"label":"G7","duration":1,"timing_unit":"beats"},{"label":"C","duration":2,"timing_unit":"beats"}]}],"annotations":{"keys":[[0,3,"C major"]]},"synthetic":true}
```

Event timing units are `seconds`, `beats`, or `unknown`; source key intervals in `annotations.keys` are evaluated against seconds only. Chord order and raw labels are always retained. Unsupported chords are preserved as unknown and reported; they are not silently interpreted as major triads. No-chord symbols are separate.

## Chordonomicon

Input: publisher CSV with `id` and `chords` columns. `<verse_1>`, `<chorus_2>`, and similar embedded tags define separate ordered sections. Optional `artist_id`, `title`, `genres`, `main_genre`, `genre`, `release_year`, and `decade` fields are preserved. Unavailable title/artist information is not reconstructed from external services.

Source and dataset terms: [publisher dataset](https://huggingface.co/datasets/ailsntua/Chordonomicon). The dataset page identifies CC-BY-NC-4.0. Cite [Kantarelis et al.](https://arxiv.org/abs/2410.22046). Review the release actually used before redistribution.

## McGill Billboard

Input: extracted directory containing an index CSV and per-song `salami_chords.txt` files. Header metadata, SALAMI section names, bar repetitions, repeated-chord dots, beat-level chord shorthand, and phrase timing are handled. Interpolated event timing is labeled in source provenance. Unsupported instrumental/annotation constructs remain visible in import reports rather than being treated as musical truth.

The [publisher documentation](https://ddmal.ca/research/The_McGill_Billboard_Project_%28Chord_Analysis_Dataset%29/) specifies the format and CC0 terms; cite Burgoyne, Wild, and Fujinaga (ISMIR 2011). Audio is not included.

## Isophonics

Input: a JSON manifest with paths relative to its directory. Referenced paths must stay inside that directory.

```json
{"songs":[{"id":"track-1","title":"Track title","artist":"Artist","chords":"chords/track-1.lab","keys":"keys/track-1.lab","sections":"segments/track-1.lab"}]}
```

The `keys` and `sections` files are optional. LAB rows contain onset seconds, offset seconds, and a label. A chord belongs to the structural interval containing its onset; original interval data is preserved. Uncovered regions become unknown sections. Different adjacent occurrences of a section remain distinct, even when they share a label.

Reference: [Isophonics annotation documentation](https://isophonics.net/content/reference-annotations.html). Users supply data and record the applicable release terms; this project does not assume unrestricted redistribution.

## Validation and versioning

Expert or constructed event references can be supplied inside `annotations`. All event indices are zero-based. `event_keys` maps event indices to keys such as `"C major"` or `"A:min"`. `event_romans` maps indices to a numeral or a list of accepted alternatives. `key_boundaries`, `modulation_boundaries`, and `cadence_boundaries` are lists of event indices. Supply an empty list only when the song was reviewed and has no such boundaries; omit the field when unannotated. Boundary metrics use a one-event tolerance and macro averaging across annotated songs. Synthetic references must still be marked synthetic.

Every file set receives a SHA-256 fingerprint. An identical source ID inside the same release is skipped on resume. A changed file set becomes a new release; use dataset filters to avoid searching alternate releases together unintentionally. Invalid song records are rejected individually; the report retains counts and up to 100 detailed errors. Database and filesystem failures fail the job rather than masquerading as invalid music data.

Source annotations are not used as local-key inference inputs. They are available to evaluation modules and to explicitly constructed query exemplars only. Artist, duplicate-group, and content relationships are combined transitively when generating split manifests.
