import json
from harmonygraph.ingestion import billboard_records, chordonomicon_records, isophonics_records


def test_chordonomicon_sections(tmp_path):
    path = tmp_path / "chords.csv"
    path.write_text("id,chords,artist_id,release_year,genre\n1,<verse_1> C G <chorus_1> Am F,artist_1,2000,pop\n")
    _, song, error = next(chordonomicon_records(path))
    assert error is None
    assert len(song["sections"]) == 2 and song["sections"][1]["label"] == "chorus_1"
    assert song["year"] == 2000


def test_billboard_repeated_chords_timing(tmp_path):
    folder = tmp_path / "0001"
    folder.mkdir()
    (folder / "salami_chords.txt").write_text(
        "# title: Test\n# artist: Test Artist\n# metre: 4/4\n0 A, verse, | C:maj . G:7 . |\n4 B, chorus, | C:maj |\n8 end\n"
    )
    _, song, error = next(billboard_records(tmp_path))
    assert error is None
    assert [e["label"] for e in song["sections"][0]["events"]] == ["C:maj", "C:maj", "G:7", "G:7"]
    assert song["sections"][0]["events"][0]["duration"] == 1
    assert song["sections"][1]["events"][0]["duration"] == 4


def test_isophonics_preserves_missing_sections_and_keys(tmp_path):
    (tmp_path / "chords.lab").write_text("0 1 C:maj\n1 3 G:7\n")
    (tmp_path / "keys.lab").write_text("0 3 C major\n")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"songs": [{"id": "one", "chords": "chords.lab", "keys": "keys.lab"}]}))
    _, song, error = next(isophonics_records(manifest))
    assert error is None
    assert song["sections"][0]["label"] == "unknown"
    assert song["annotations"]["keys"][0][2] == "C major"
