# tests/export/test_grain_json_writer.py
"""
TDD suite per GrainJsonWriter.

Esporta i grani di uno stream in JSON consumabile da un client di
visualizzazione (PGE-ui). Un file per stream.

Schema JSON prodotto (compatto, senza whitespace):
  {"stream_id":"s1","duration":8.0,"num_voices":4,
   "grains":[{"t":0.0,"dur":0.08,"vol":-6.0,"ptr":0.34,"v":0}, ...]}

  - t   = grain.onset - stream.onset  (relativo allo stream; puo' essere < 0)
  - dur = grain.duration
  - vol = grain.volume
  - ptr = grain.pointer_pos
  - v   = indice voce (da stream.voices)
  grains ordinati per t crescente.

Sezioni:
1. TestTopLevelStructure - chiavi top-level e metadati stream
2. TestGrainMapping      - mappatura campi grano e indice voce
3. TestOrdering          - grani ordinati per t
4. TestCompactJson       - JSON compatto, niente whitespace
5. TestWriteToDisk       - write() crea il file, contenuto == generate()
6. TestEdgeCases         - stream senza grani, t negativo
"""

import json
import pytest
from unittest.mock import Mock

from export.grain_json_writer import GrainJsonWriter


# =============================================================================
# FIXTURES
# =============================================================================

def _make_grain(onset, duration=0.08, volume=-6.0, pointer_pos=0.0):
    g = Mock()
    g.onset = onset
    g.duration = duration
    g.volume = volume
    g.pointer_pos = pointer_pos
    return g


def _make_stream(stream_id, onset, duration, voices):
    """voices: List[List[grain]] - una lista di grani per voce."""
    s = Mock()
    s.stream_id = stream_id
    s.onset = onset
    s.duration = duration
    s.voices = voices
    return s


@pytest.fixture
def writer():
    return GrainJsonWriter()


@pytest.fixture
def two_voice_stream():
    # voce 0: due grani; voce 1: un grano
    return _make_stream(
        "s1", onset=10.0, duration=8.0,
        voices=[
            [_make_grain(10.0, pointer_pos=0.34), _make_grain(11.0, pointer_pos=0.5)],
            [_make_grain(10.5, pointer_pos=0.1)],
        ],
    )


# =============================================================================
# 1. STRUTTURA TOP-LEVEL
# =============================================================================

class TestTopLevelStructure:
    """Chiavi top-level: stream_id, duration, num_voices, grains."""

    def test_stream_id_in_output(self, writer, two_voice_stream):
        data = writer.build(two_voice_stream)
        assert data["stream_id"] == "s1"

    def test_duration_in_output(self, writer, two_voice_stream):
        data = writer.build(two_voice_stream)
        assert data["duration"] == 8.0

    def test_num_voices_matches_voices_length(self, writer, two_voice_stream):
        """num_voices riflette il numero di voci effettivamente generate."""
        data = writer.build(two_voice_stream)
        assert data["num_voices"] == 2

    def test_grains_is_a_list(self, writer, two_voice_stream):
        data = writer.build(two_voice_stream)
        assert isinstance(data["grains"], list)

    def test_grain_count_is_total_across_voices(self, writer, two_voice_stream):
        data = writer.build(two_voice_stream)
        assert len(data["grains"]) == 3


# =============================================================================
# 2. MAPPATURA CAMPI GRANO
# =============================================================================

class TestGrainMapping:
    """Ogni grano mappa t/dur/vol/ptr/v correttamente."""

    def test_t_relative_to_stream_onset(self, writer):
        stream = _make_stream("s1", onset=10.0, duration=4.0,
                              voices=[[_make_grain(12.5)]])
        data = writer.build(stream)
        assert data["grains"][0]["t"] == pytest.approx(2.5)

    def test_dur_maps_grain_duration(self, writer):
        stream = _make_stream("s1", onset=0.0, duration=4.0,
                              voices=[[_make_grain(0.0, duration=0.123)]])
        data = writer.build(stream)
        assert data["grains"][0]["dur"] == pytest.approx(0.123)

    def test_vol_maps_grain_volume(self, writer):
        stream = _make_stream("s1", onset=0.0, duration=4.0,
                              voices=[[_make_grain(0.0, volume=-12.5)]])
        data = writer.build(stream)
        assert data["grains"][0]["vol"] == pytest.approx(-12.5)

    def test_ptr_maps_grain_pointer_pos(self, writer):
        stream = _make_stream("s1", onset=0.0, duration=4.0,
                              voices=[[_make_grain(0.0, pointer_pos=0.42)]])
        data = writer.build(stream)
        assert data["grains"][0]["ptr"] == pytest.approx(0.42)

    def test_voice_index_recorded(self, writer):
        """Il campo v corrisponde all'indice della voce in stream.voices."""
        stream = _make_stream("s1", onset=0.0, duration=4.0,
                              voices=[[_make_grain(0.0)], [_make_grain(0.0)]])
        data = writer.build(stream)
        voices_seen = {g["v"] for g in data["grains"]}
        assert voices_seen == {0, 1}


# =============================================================================
# 3. ORDINAMENTO
# =============================================================================

class TestOrdering:
    """I grani sono ordinati per t crescente, anche tra voci diverse."""

    def test_grains_sorted_by_t(self, writer):
        stream = _make_stream("s1", onset=0.0, duration=10.0,
                              voices=[[_make_grain(5.0)], [_make_grain(1.0)], [_make_grain(3.0)]])
        data = writer.build(stream)
        ts = [g["t"] for g in data["grains"]]
        assert ts == sorted(ts)


# =============================================================================
# 4. JSON COMPATTO
# =============================================================================

class TestCompactJson:
    """generate() produce JSON valido e compatto (no whitespace)."""

    def test_generate_returns_valid_json(self, writer, two_voice_stream):
        text = writer.generate(two_voice_stream)
        parsed = json.loads(text)
        assert parsed["stream_id"] == "s1"

    def test_generate_has_no_whitespace(self, writer, two_voice_stream):
        text = writer.generate(two_voice_stream)
        assert ", " not in text
        assert ": " not in text


# =============================================================================
# 5. SCRITTURA SU DISCO
# =============================================================================

class TestWriteToDisk:
    """write() crea il file; il contenuto coincide con generate()."""

    def test_write_creates_file(self, writer, two_voice_stream, tmp_path):
        path = writer.write(two_voice_stream, str(tmp_path), "myconfig")
        import os
        assert os.path.exists(path)

    def test_write_filename_contains_basename_and_stream_id(self, writer, two_voice_stream, tmp_path):
        path = writer.write(two_voice_stream, str(tmp_path), "myconfig")
        name = str(path)
        assert "myconfig" in name and "s1" in name and name.endswith(".json")

    def test_write_content_matches_generate(self, writer, two_voice_stream, tmp_path):
        path = writer.write(two_voice_stream, str(tmp_path), "myconfig")
        assert open(path).read() == writer.generate(two_voice_stream)


# =============================================================================
# 6. EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Stream senza grani, t negativo (onset offset per-voce)."""

    def test_stream_without_grains(self, writer):
        stream = _make_stream("empty", onset=0.0, duration=4.0, voices=[])
        data = writer.build(stream)
        assert data["grains"] == []
        assert data["num_voices"] == 0

    def test_voice_with_empty_grain_list(self, writer):
        stream = _make_stream("s1", onset=0.0, duration=4.0, voices=[[], []])
        data = writer.build(stream)
        assert data["grains"] == []
        assert data["num_voices"] == 2

    def test_negative_t_allowed(self, writer):
        """Onset offset per-voce puo' produrre grani con onset < stream.onset."""
        stream = _make_stream("s1", onset=10.0, duration=4.0,
                              voices=[[_make_grain(9.5)]])
        data = writer.build(stream)
        assert data["grains"][0]["t"] == pytest.approx(-0.5)
