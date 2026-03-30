# tests/export/test_reaper_project_writer.py
"""
TDD suite per ReaperProjectWriter.

Genera un file .rpp (Reaper DAW project) a partire da stream e path .aif.

Struttura .rpp prodotta:
  <REAPER_PROJECT ...
    <TRACK
      NAME "stream_id"
      <ITEM
        POSITION <onset>
        LENGTH   <duration>
        <SOURCE WAVE
          FILE "path/to/file.aif"
        >
      >
    >
  >

Sezioni:
1. TestRPPStructure      - struttura generale del file .rpp
2. TestTrackGeneration   - un TRACK per stream
3. TestItemAttributes    - POSITION e LENGTH da onset/duration
4. TestFileReference     - FILE referenzia il path .aif corretto
5. TestEdgeCases         - lista vuota, stream singolo, path assoluti/relativi
"""

import pytest
from unittest.mock import Mock

from export.reaper_project_writer import ReaperProjectWriter


# =============================================================================
# FIXTURES
# =============================================================================

def _make_stream(stream_id, onset, duration):
    s = Mock()
    s.stream_id = stream_id
    s.onset = onset
    s.duration = duration
    return s


@pytest.fixture
def writer():
    return ReaperProjectWriter()


@pytest.fixture
def single_stream():
    return _make_stream("stream1", onset=0.0, duration=10.0)


@pytest.fixture
def two_streams():
    return [
        _make_stream("s1", onset=0.0, duration=5.0),
        _make_stream("s2", onset=5.0, duration=8.0),
    ]


# =============================================================================
# 1. STRUTTURA GENERALE
# =============================================================================

class TestRPPStructure:
    """Il file .rpp inizia con REAPER_PROJECT e termina con >."""

    def test_output_starts_with_reaper_project(self, writer, two_streams):
        """Il contenuto inizia con il tag <REAPER_PROJECT."""
        content = writer.generate(two_streams, ["s1.aif", "s2.aif"])
        assert content.startswith("<REAPER_PROJECT")

    def test_output_ends_with_closing_bracket(self, writer, two_streams):
        """Il contenuto termina con il tag di chiusura >."""
        content = writer.generate(two_streams, ["s1.aif", "s2.aif"])
        assert content.strip().endswith(">")

    def test_write_creates_file_on_disk(self, writer, two_streams, tmp_path):
        """write() crea il file .rpp su disco."""
        rpp_path = str(tmp_path / "project.rpp")
        writer.write(two_streams, ["s1.aif", "s2.aif"], rpp_path)
        import os
        assert os.path.exists(rpp_path)

    def test_write_file_content_matches_generate(self, writer, two_streams, tmp_path):
        """Il contenuto del file scritto è identico a generate()."""
        rpp_path = str(tmp_path / "project.rpp")
        writer.write(two_streams, ["s1.aif", "s2.aif"], rpp_path)
        expected = writer.generate(two_streams, ["s1.aif", "s2.aif"])
        assert open(rpp_path).read() == expected


# =============================================================================
# 2. TRACK GENERATION
# =============================================================================

class TestTrackGeneration:
    """Un blocco TRACK per ogni stream."""

    def test_one_track_per_stream(self, writer, two_streams):
        """Il numero di blocchi TRACK corrisponde al numero di stream."""
        content = writer.generate(two_streams, ["s1.aif", "s2.aif"])
        assert content.count("<TRACK") == 2

    def test_track_contains_stream_name(self, writer, single_stream):
        """Il TRACK contiene il NAME con lo stream_id."""
        content = writer.generate([single_stream], ["out.aif"])
        assert 'NAME "stream1"' in content

    def test_empty_stream_list_produces_empty_project(self, writer):
        """Lista vuota: nessun TRACK nel progetto."""
        content = writer.generate([], [])
        assert "<TRACK" not in content

    def test_track_order_matches_stream_order(self, writer, two_streams):
        """L'ordine dei TRACK rispecchia l'ordine degli stream."""
        content = writer.generate(two_streams, ["s1.aif", "s2.aif"])
        pos_s1 = content.index('NAME "s1"')
        pos_s2 = content.index('NAME "s2"')
        assert pos_s1 < pos_s2


# =============================================================================
# 3. ITEM ATTRIBUTES
# =============================================================================

class TestItemAttributes:
    """POSITION e LENGTH derivati da stream.onset e stream.duration."""

    def test_item_position_matches_stream_onset(self, writer, single_stream):
        """POSITION corrisponde a stream.onset."""
        content = writer.generate([single_stream], ["out.aif"])
        assert "POSITION 0.0" in content

    def test_item_length_matches_stream_duration(self, writer, single_stream):
        """LENGTH corrisponde a stream.duration."""
        content = writer.generate([single_stream], ["out.aif"])
        assert "LENGTH 10.0" in content

    def test_item_position_non_zero_onset(self, writer):
        """POSITION corretta per stream con onset != 0."""
        stream = _make_stream("s2", onset=5.5, duration=3.0)
        content = writer.generate([stream], ["s2.aif"])
        assert "POSITION 5.5" in content

    def test_each_track_has_one_item(self, writer, two_streams):
        """Ogni TRACK contiene esattamente un blocco ITEM."""
        content = writer.generate(two_streams, ["s1.aif", "s2.aif"])
        assert content.count("<ITEM") == 2

    def test_item_uses_wave_source(self, writer, single_stream):
        """Il blocco SOURCE usa il tipo WAVE."""
        content = writer.generate([single_stream], ["out.aif"])
        assert "<SOURCE WAVE" in content


# =============================================================================
# 4. FILE REFERENCE
# =============================================================================

class TestFileReference:
    """FILE referenzia il path .aif corretto per ogni stream."""

    def test_file_reference_matches_aif_path(self, writer, single_stream):
        """FILE referenzia il path .aif fornito."""
        content = writer.generate([single_stream], ["output/stream1.aif"])
        assert 'FILE "output/stream1.aif"' in content

    def test_each_track_references_correct_file(self, writer, two_streams):
        """Ogni TRACK referenzia il file .aif corrispondente."""
        content = writer.generate(two_streams, ["out/s1.aif", "out/s2.aif"])
        assert 'FILE "out/s1.aif"' in content
        assert 'FILE "out/s2.aif"' in content

    def test_absolute_path_preserved(self, writer, single_stream):
        """Path assoluti vengono preservati nel FILE tag."""
        content = writer.generate([single_stream], ["/tmp/output/stream1.aif"])
        assert 'FILE "/tmp/output/stream1.aif"' in content

    def test_file_inside_source_block(self, writer, single_stream):
        """FILE appare dentro il blocco SOURCE WAVE."""
        content = writer.generate([single_stream], ["out.aif"])
        source_start = content.index("<SOURCE WAVE")
        file_pos = content.index('FILE "out.aif"')
        # FILE deve venire dopo SOURCE
        assert file_pos > source_start


# =============================================================================
# 5. EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Casi limite: stream singolo, onset=0, duration molto piccola."""

    def test_single_stream_single_track(self, writer, single_stream):
        """Un solo stream produce esattamente un TRACK."""
        content = writer.generate([single_stream], ["out.aif"])
        assert content.count("<TRACK") == 1

    def test_zero_onset_stream(self, writer):
        """Stream con onset=0 produce POSITION 0.0."""
        stream = _make_stream("s1", onset=0.0, duration=1.0)
        content = writer.generate([stream], ["s1.aif"])
        assert "POSITION 0.0" in content

    def test_fractional_duration(self, writer):
        """Duration con decimali viene preservata correttamente."""
        stream = _make_stream("s1", onset=1.5, duration=0.125)
        content = writer.generate([stream], ["s1.aif"])
        assert "LENGTH 0.125" in content

    def test_streams_and_paths_count_mismatch_raises(self, writer, two_streams):
        """Numero di stream e path diversi solleva ValueError."""
        with pytest.raises(ValueError):
            writer.generate(two_streams, ["only_one.aif"])
