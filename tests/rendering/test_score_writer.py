"""
Test suite completa per score_writer.py

Testa la classe ScoreWriter e tutti i suoi metodi:
- write_score: orchestrazione scrittura completa
- _write_header: intestazione file score
- _write_events: dispatch eventi (streams + cartridges)
- _write_footer: chiusura file score
- _write_granular_streams: sezione stream granulari
- _write_stream_section: sezione singolo stream
- _write_stream_metadata: metadati stream come commenti
- _write_tape_recorder_cartridges: sezione cartridges
- _write_cartridge_section: sezione singola cartridge
- _format_param: formattazione parametri per commenti
- _print_generation_summary: riepilogo generazione

Strategia di mocking:
- FtableManager: mock completo (dependency injection)
- Stream/cartridge: mock con attributi necessari
- Parameter/Envelope: mock per test _format_param
- File I/O: StringIO per catturare output
"""

import pytest
import io
import os
import sys
from unittest.mock import Mock, MagicMock, patch, call

# =============================================================================
# MOCK INFRASTRUCTURE
# =============================================================================

# NOTA CRITICA SULLA STRATEGIA DI IMPORT
# ========================================
# test_window_controller.py inietta classi mock in sys.modules['probability_gate']
# PRIMA di importare WindowController. Se noi importiamo Parameter o Envelope
# a livello top-level, il modulo reale probability_gate viene caricato in sys.modules
# e sovrascrive i mock di test_window_controller.
#
# Soluzione: TUTTI gli import di moduli di produzione avvengono lazy (dentro funzioni),
# mai a livello di modulo. Anche ScoreWriter viene importato lazy.
# Questo garantisce che il semplice "collect" di pytest non contamini sys.modules.

# Cache per import lazy (evita import ripetuti)
_import_cache = {}


def _get_score_writer_class():
    """Import lazy di ScoreWriter."""
    if 'ScoreWriter' not in _import_cache:
        from rendering.score_writer import ScoreWriter
        _import_cache['ScoreWriter'] = ScoreWriter
    return _import_cache['ScoreWriter']


def _get_real_parameter():
    """Import lazy di Parameter."""
    if 'Parameter' not in _import_cache:
        from parameters.parameter import Parameter
        _import_cache['Parameter'] = Parameter
    return _import_cache['Parameter']


def _get_real_envelope():
    """Import lazy di Envelope."""
    if 'Envelope' not in _import_cache:
        from envelopes.envelope import Envelope
        _import_cache['Envelope'] = Envelope
    return _import_cache['Envelope']


# Cache per la classe MockParameter (creata lazy)
_MockParameterClass = None


def _make_mock_parameter_instance(value, name='mock_param'):
    """
    Crea un mock Parameter che passa isinstance(obj, Parameter).
    
    Usa type() per creare una sottoclasse al volo dal Parameter reale.
    type() crea la classe con il layout di memoria corretto (a differenza
    di __bases__ assignment che fallisce con 'deallocator differs from object').
    """
    global _MockParameterClass

    if _MockParameterClass is None:
        RealParam = _get_real_parameter()

        def _init(self, value, name='mock_param'):
            # Bypass completo del costruttore reale
            self._value = value
            self.name = name
            self.owner_id = 'test'
            self._bounds = None
            self._mod_range = None
            self._probability_gate = None
            self._distribution = None
            self._variation_strategy = None

        def _get_value(self, time: float) -> float:
            if hasattr(self._value, 'evaluate'):
                return self._value.evaluate(time)
            return float(self._value) if self._value is not None else 0.0

        def _value_prop(self):
            return self._value

        _MockParameterClass = type('MockParameter', (RealParam,), {
            '__init__': _init,
            'get_value': _get_value,
            'value': property(_value_prop),
        })

    return _MockParameterClass(value, name)


def make_real_envelope(breakpoints=None):
    """
    Crea un Envelope REALE con breakpoints minimi.
    """
    RealEnv = _get_real_envelope()
    bp = breakpoints or [[0.0, 0.5], [10.0, 1.0]]
    return RealEnv(bp)


def make_mock_grain(onset=0.0, duration=0.05, score_line=None):
    """Crea un mock Grain con to_score_line()."""
    grain = Mock()
    grain.onset = onset
    grain.duration = duration
    if score_line is None:
        score_line = (
            f'i "Grain" {onset:.6f} {duration:.6f} '
            f'1.000000 1.000000 -6.00 0.500 1 2\n'
        )
    grain.to_score_line.return_value = score_line
    return grain


def make_mock_stream(
    stream_id='stream_01',
    grain_duration=0.05,
    density=10.0,
    distribution=0.5,
    num_voices=2,
    voices=None,
):
    """
    Crea un mock Stream con tutti gli attributi necessari per ScoreWriter.
    
    Args:
        stream_id: ID dello stream
        grain_duration: durata grani (float, Parameter, o Envelope)
        density: densita' (float, Parameter, o Envelope)
        distribution: distribuzione (float)
        num_voices: numero voci (int, Parameter, o Envelope)
        voices: List[List[Grain]] - se None, crea 2 voice con 3 grani ciascuna
    """
    stream = Mock()
    stream.stream_id = stream_id
    stream.grain_duration = grain_duration
    stream.density = density
    stream.distribution = distribution
    stream.num_voices = num_voices

    if voices is None:
        voice_0 = [make_mock_grain(i * 0.1, 0.05) for i in range(3)]
        voice_1 = [make_mock_grain(i * 0.1 + 0.02, 0.05) for i in range(3)]
        voices = [voice_0, voice_1]

    stream.voices = voices
    return stream


def make_mock_cartridge(
    cartridge_id='cartridge_01',
    sample_path='sample.wav',
    speed=1.0,
    duration=5.0,
    score_line=None,
):
    """Crea un mock cartridge con tutti gli attributi necessari."""
    cartridge = Mock()
    cartridge.cartridge_id = cartridge_id
    cartridge.sample_path = sample_path
    cartridge.speed = speed
    cartridge.duration = duration
    if score_line is None:
        score_line = (
            f'i "TapeRecorder" 0.000000 {duration:.6f} '
            f'0.000000 {speed:.6f} 0.00 0.500 0 0.000000 -1.000000 1\n'
        )
    cartridge.to_score_line.return_value = score_line
    return cartridge


def make_mock_ftable_manager(num_tables=3):
    """Crea un mock FtableManager."""
    ftm = Mock()
    tables = {i: ('sample', f'sample_{i}.wav') for i in range(1, num_tables + 1)}
    ftm.get_all_tables.return_value = tables
    ftm.write_to_file = Mock()
    return ftm


# =============================================================================
# IMPORT MODULE UNDER TEST (LAZY)
# =============================================================================

# ScoreWriter viene importato lazy tramite _get_score_writer_class()
# Non facciamo import top-level per non contaminare sys.modules.


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def ftable_manager():
    """FtableManager mock base."""
    return make_mock_ftable_manager()


@pytest.fixture
def writer(ftable_manager):
    """ScoreWriter con FtableManager mock."""
    ScoreWriter = _get_score_writer_class()
    return ScoreWriter(ftable_manager)


@pytest.fixture
def string_file():
    """StringIO che simula un file handle aperto."""
    return io.StringIO()


@pytest.fixture
def sample_stream():
    """Stream mock base con 2 voices, 3 grani ciascuna."""
    return make_mock_stream()


@pytest.fixture
def sample_cartridge():
    """cartridge mock base."""
    return make_mock_cartridge()


# =============================================================================
# 1. TEST INIZIALIZZAZIONE
# =============================================================================

class TestScoreWriterInit:
    """Test costruttore ScoreWriter."""

    def test_init_stores_ftable_manager(self, ftable_manager):
        """Il costruttore salva il riferimento a FtableManager."""
        SW = _get_score_writer_class()
        sw = SW(ftable_manager)
        assert sw.ftable_manager is ftable_manager

    def test_init_with_different_ftable_managers(self):
        """Verifica che accetti qualunque FtableManager."""
        SW = _get_score_writer_class()
        ftm1 = make_mock_ftable_manager(1)
        ftm2 = make_mock_ftable_manager(10)

        sw1 = SW(ftm1)
        sw2 = SW(ftm2)

        assert sw1.ftable_manager is ftm1
        assert sw2.ftable_manager is ftm2
        assert sw1.ftable_manager is not sw2.ftable_manager


# =============================================================================
# 2. TEST _write_header
# =============================================================================

class TestWriteHeader:
    """Test per _write_header."""

    def test_header_contains_csound_score_label(self, writer, string_file):
        """L'header contiene la label CSOUND SCORE."""
        writer._write_header(string_file)
        content = string_file.getvalue()

        assert "; CSOUND SCORE" in content

    def test_header_contains_separator_lines(self, writer, string_file):
        """L'header contiene linee separatrici con '='."""
        writer._write_header(string_file)
        content = string_file.getvalue()

        assert "; =" in content

    def test_header_with_yaml_source(self, writer, string_file):
        """Con yaml_source, l'header include il percorso sorgente."""
        writer._write_header(string_file, yaml_source='config/test.yml')
        content = string_file.getvalue()

        assert "; Generated from: config/test.yml" in content

    def test_header_without_yaml_source(self, writer, string_file):
        """Senza yaml_source, non c'e' la riga Generated from."""
        writer._write_header(string_file)
        content = string_file.getvalue()

        assert "Generated from" not in content

    def test_header_ends_with_blank_line(self, writer, string_file):
        """L'header termina con una riga vuota per separazione."""
        writer._write_header(string_file)
        content = string_file.getvalue()

        assert content.endswith("\n\n")


# =============================================================================
# 3. TEST _write_footer
# =============================================================================

class TestWriteFooter:
    """Test per _write_footer."""

    def test_footer_contains_end_label(self, writer, string_file):
        """Il footer contiene la label End of score."""
        writer._write_footer(string_file)
        content = string_file.getvalue()

        assert "; End of score" in content

    def test_footer_contains_e_statement(self, writer, string_file):
        """Il footer contiene lo statement 'e' di Csound per terminare lo score."""
        writer._write_footer(string_file)
        content = string_file.getvalue()

        assert "e\n" in content

    def test_footer_e_is_last_line(self, writer, string_file):
        """'e' e' l'ultima riga del footer."""
        writer._write_footer(string_file)
        content = string_file.getvalue()

        assert content.strip().endswith("e")

    def test_footer_contains_separator(self, writer, string_file):
        """Il footer contiene separatori con '='."""
        writer._write_footer(string_file)
        content = string_file.getvalue()

        assert "; =" in content


# =============================================================================
# 4. TEST _write_events
# =============================================================================

class TestWriteEvents:
    """Test per _write_events (dispatch)."""

    def test_events_with_streams_only(self, writer, string_file, sample_stream):
        """Con solo streams, scrive solo la sezione granulare."""
        writer._write_events(string_file, [sample_stream], [])
        content = string_file.getvalue()

        assert "GRANULAR STREAMS" in content
        assert "TAPE RECORDER" not in content

    def test_events_with_cartridges_only(self, writer, string_file, sample_cartridge):
        """Con solo cartridges, scrive solo la sezione tape recorder."""
        writer._write_events(string_file, [], [sample_cartridge])
        content = string_file.getvalue()

        assert "TAPE RECORDER" in content
        assert "GRANULAR STREAMS" not in content

    def test_events_with_both(self, writer, string_file, sample_stream, sample_cartridge):
        """Con entrambi, scrive entrambe le sezioni."""
        writer._write_events(string_file, [sample_stream], [sample_cartridge])
        content = string_file.getvalue()

        assert "GRANULAR STREAMS" in content
        assert "TAPE RECORDER" in content

    def test_events_with_empty_lists(self, writer, string_file):
        """Con liste vuote, non scrive nulla."""
        writer._write_events(string_file, [], [])
        content = string_file.getvalue()

        assert content == ""

    def test_events_streams_before_cartridges(self, writer, string_file, sample_stream, sample_cartridge):
        """Gli stream vengono scritti prima delle cartridges."""
        writer._write_events(string_file, [sample_stream], [sample_cartridge])
        content = string_file.getvalue()

        gran_pos = content.index("GRANULAR STREAMS")
        tape_pos = content.index("TAPE RECORDER")
        assert gran_pos < tape_pos


# =============================================================================
# 5. TEST _write_granular_streams
# =============================================================================

class TestWriteGranularStreams:
    """Test per _write_granular_streams."""

    def test_section_header(self, writer, string_file, sample_stream):
        """La sezione inizia con header GRANULAR STREAMS."""
        writer._write_granular_streams(string_file, [sample_stream])
        content = string_file.getvalue()

        assert "; GRANULAR STREAMS" in content

    def test_multiple_streams(self, writer, string_file):
        """Scrive correttamente piu' stream."""
        s1 = make_mock_stream(stream_id='stream_A')
        s2 = make_mock_stream(stream_id='stream_B')

        writer._write_granular_streams(string_file, [s1, s2])
        content = string_file.getvalue()

        assert "; Stream: stream_A" in content
        assert "; Stream: stream_B" in content

    def test_single_stream(self, writer, string_file):
        """Scrive correttamente un singolo stream."""
        s = make_mock_stream(stream_id='solo_stream')
        writer._write_granular_streams(string_file, [s])
        content = string_file.getvalue()

        assert "; Stream: solo_stream" in content


# =============================================================================
# 6. TEST _write_stream_section
# =============================================================================

class TestWriteStreamSection:
    """Test per _write_stream_section."""

    def test_stream_id_in_header(self, writer, string_file):
        """L'ID dello stream appare nell'header."""
        stream = make_mock_stream(stream_id='texture_01')
        writer._write_stream_section(string_file, stream)
        content = string_file.getvalue()

        assert "; Stream: texture_01" in content

    def test_voice_labels_present(self, writer, string_file, sample_stream):
        """Le label delle voice sono presenti nel contenuto."""
        writer._write_stream_section(string_file, sample_stream)
        content = string_file.getvalue()

        assert "; " in content
        assert "Voice 0" in content
        assert "Voice 1" in content

    def test_voice_grain_count(self, writer, string_file, sample_stream):
        """Il conteggio grani per voice appare correttamente."""
        writer._write_stream_section(string_file, sample_stream)
        content = string_file.getvalue()

        assert "3 grains" in content

    def test_empty_voice_skipped(self, writer, string_file):
        """Una voice senza grani viene saltata."""
        stream = make_mock_stream(
            voices=[
                [make_mock_grain()],  # voice 0: 1 grano
                [],                    # voice 1: vuota
            ]
        )
        writer._write_stream_section(string_file, stream)
        content = string_file.getvalue()

        assert "Voice 0" in content
        assert "Voice 1" not in content

    def test_grain_score_lines_written(self, writer, string_file):
        """Le score line dei grani vengono effettivamente scritte."""
        grain = make_mock_grain(
            score_line='i "Grain" 0.100000 0.050000 1.0 1.0 -6.00 0.500 1 2\n'
        )
        stream = make_mock_stream(voices=[[grain]])
        writer._write_stream_section(string_file, stream)
        content = string_file.getvalue()

        assert 'i "Grain"' in content
        grain.to_score_line.assert_called_once()

    def test_all_grains_written(self, writer, string_file):
        """Tutti i grani di tutte le voice vengono scritti."""
        grains_v0 = [make_mock_grain(i * 0.1) for i in range(5)]
        grains_v1 = [make_mock_grain(i * 0.1) for i in range(3)]
        stream = make_mock_stream(voices=[grains_v0, grains_v1])

        writer._write_stream_section(string_file, stream)

        for g in grains_v0 + grains_v1:
            g.to_score_line.assert_called_once()


# =============================================================================
# 7. TEST _write_stream_metadata
# =============================================================================

class TestWriteStreamMetadata:
    """Test per _write_stream_metadata."""

    def test_grain_duration_displayed(self, writer, string_file, sample_stream):
        """La durata grani appare nei metadati."""
        writer._write_stream_metadata(string_file, sample_stream)
        content = string_file.getvalue()

        assert "; Grain duration:" in content

    def test_density_displayed(self, writer, string_file, sample_stream):
        """La densita' appare nei metadati."""
        writer._write_stream_metadata(string_file, sample_stream)
        content = string_file.getvalue()

        assert "; Density:" in content

    def test_distribution_displayed(self, writer, string_file, sample_stream):
        """La distribuzione appare nei metadati."""
        writer._write_stream_metadata(string_file, sample_stream)
        content = string_file.getvalue()

        assert "; Distribution:" in content

    def test_num_voices_displayed(self, writer, string_file, sample_stream):
        """Il numero di voci appare nei metadati."""
        writer._write_stream_metadata(string_file, sample_stream)
        content = string_file.getvalue()

        assert "; Num voices:" in content

    def test_total_grains_displayed(self, writer, string_file, sample_stream):
        """Il totale grani appare nei metadati."""
        writer._write_stream_metadata(string_file, sample_stream)
        content = string_file.getvalue()

        assert "; Total grains:" in content

    def test_total_grains_count_correct(self, writer, string_file):
        """Il conteggio totale grani e' la somma di tutte le voice."""
        grains_v0 = [make_mock_grain() for _ in range(5)]
        grains_v1 = [make_mock_grain() for _ in range(7)]
        stream = make_mock_stream(voices=[grains_v0, grains_v1])

        writer._write_stream_metadata(string_file, stream)
        content = string_file.getvalue()

        assert "; Total grains: 12" in content

    def test_metadata_with_float_values(self, writer, string_file):
        """Metadati con valori numerici semplici."""
        stream = make_mock_stream(
            grain_duration=0.025,
            density=50.0,
            distribution=0.8,
            num_voices=4,
        )
        writer._write_stream_metadata(string_file, stream)
        content = string_file.getvalue()

        # grain_duration * 1000 = 25.0ms
        assert "25.0ms" in content
        # density * 1 = 50.0 g/s
        assert "50.0 g/s" in content

    def test_metadata_with_parameter_num_voices(self, writer, string_file):
        """Metadati con num_voices come Parameter."""
        mock_param = _make_mock_parameter_instance(value=4.0, name='num_voices')
        stream = make_mock_stream(num_voices=mock_param)

        writer._write_stream_metadata(string_file, stream)
        content = string_file.getvalue()

        # Deve passare per il branch isinstance(Parameter, Envelope)
        assert "; Num voices:" in content

    def test_metadata_with_envelope_num_voices(self, writer, string_file):
        """Metadati con num_voices come Envelope."""
        mock_env = make_real_envelope([[0.0, 2.0], [10.0, 8.0]])
        stream = make_mock_stream(num_voices=mock_env)

        writer._write_stream_metadata(string_file, stream)
        content = string_file.getvalue()

        assert "; Num voices:" in content
        assert "dynamic" in content

    def test_metadata_with_integer_num_voices(self, writer, string_file):
        """Metadati con num_voices come intero diretto."""
        stream = make_mock_stream(num_voices=3)
        writer._write_stream_metadata(string_file, stream)
        content = string_file.getvalue()

        assert "; Num voices: 3" in content

    def test_metadata_with_parameter_grain_duration(self, writer, string_file):
        """Metadati con grain_duration come Parameter."""
        mock_param = _make_mock_parameter_instance(value=0.03, name='grain_duration')
        stream = make_mock_stream(grain_duration=mock_param)

        writer._write_stream_metadata(string_file, stream)
        content = string_file.getvalue()

        # Parameter._value = 0.03, _format_param estrae e moltiplica *1000 = 30.0ms
        assert "30.0ms" in content

    def test_metadata_with_envelope_grain_duration(self, writer, string_file):
        """Metadati con grain_duration come Envelope (via Parameter)."""
        mock_env = make_real_envelope([[0.0, 0.01], [5.0, 0.1]])
        mock_param = _make_mock_parameter_instance(value=mock_env, name='grain_duration')
        stream = make_mock_stream(grain_duration=mock_param)

        writer._write_stream_metadata(string_file, stream)
        content = string_file.getvalue()

        assert "dynamic" in content


# =============================================================================
# 8. TEST _write_tape_recorder_cartridges
# =============================================================================

class TestWriteTapeRecordercartridges:
    """Test per _write_tape_recorder_cartridges."""

    def test_section_header(self, writer, string_file, sample_cartridge):
        """La sezione inizia con header TAPE RECORDER TRACKS."""
        writer._write_tape_recorder_cartridges(string_file, [sample_cartridge])
        content = string_file.getvalue()

        assert "; TAPE RECORDER TRACKS" in content

    def test_multiple_cartridges(self, writer, string_file):
        """Scrive correttamente piu' cartridges."""
        t1 = make_mock_cartridge(cartridge_id='rec_A')
        t2 = make_mock_cartridge(cartridge_id='rec_B')

        writer._write_tape_recorder_cartridges(string_file, [t1, t2])
        content = string_file.getvalue()

        assert "; Cartridge: rec_A" in content
        assert "; Cartridge: rec_B" in content

    def test_single_cartridge(self, writer, string_file):
        """Scrive correttamente una singola cartridge."""
        t = make_mock_cartridge(cartridge_id='solo_rec')
        writer._write_tape_recorder_cartridges(string_file, [t])
        content = string_file.getvalue()

        assert "; Cartridge: solo_rec" in content


# =============================================================================
# 9. TEST _write_cartridge_section
# =============================================================================

class TestWritecartridgeSection:
    """Test per _write_cartridge_section."""

    def test_cartridge_id_in_header(self, writer, string_file):
        """L'ID della cartridge appare nell'header."""
        cartridge = make_mock_cartridge(cartridge_id='tape_head_01')
        writer._write_cartridge_section(string_file, cartridge)
        content = string_file.getvalue()

        assert "; Cartridge: tape_head_01" in content

    def test_sample_path_in_metadata(self, writer, string_file):
        """Il path del sample appare nei metadati."""
        cartridge = make_mock_cartridge(sample_path='refs/piano.wav')
        writer._write_cartridge_section(string_file, cartridge)
        content = string_file.getvalue()

        assert "; Sample: refs/piano.wav" in content

    def test_speed_in_metadata(self, writer, string_file):
        """La velocita' appare nei metadati."""
        cartridge = make_mock_cartridge(speed=0.5)
        writer._write_cartridge_section(string_file, cartridge)
        content = string_file.getvalue()

        assert "; Speed: 0.5x" in content

    def test_duration_in_metadata(self, writer, string_file):
        """La durata appare nei metadati."""
        cartridge = make_mock_cartridge(duration=12.5)
        writer._write_cartridge_section(string_file, cartridge)
        content = string_file.getvalue()

        assert "; Duration: 12.5s" in content

    def test_score_line_written(self, writer, string_file):
        """La score line della cartridge viene scritta."""
        custom_line = 'i "TapeRecorder" 0.000000 5.000000 0.000000 1.000000 0.00 0.500 0 0.000000 -1.000000 1\n'
        cartridge = make_mock_cartridge(score_line=custom_line)
        writer._write_cartridge_section(string_file, cartridge)
        content = string_file.getvalue()

        assert 'i "TapeRecorder"' in content
        cartridge.to_score_line.assert_called_once()


# =============================================================================
# 10. TEST _format_param
# =============================================================================

class TestFormatParam:
    """Test per _format_param (utility formattazione parametri)."""

    def test_format_none_returns_na(self, writer):
        """None restituisce 'N/A'."""
        assert writer._format_param(None) == "N/A"

    def test_format_simple_float(self, writer):
        """Un float semplice viene formattato correttamente."""
        result = writer._format_param(0.05, 1000, "ms")
        assert result == "50.0ms"

    def test_format_float_with_unit(self, writer):
        """Formattazione con unita' di misura."""
        result = writer._format_param(20.0, 1, " g/s")
        assert result == "20.0 g/s"

    def test_format_float_no_multiplier(self, writer):
        """Formattazione senza moltiplicatore (default 1.0)."""
        result = writer._format_param(0.7)
        assert result == "0.7"

    def test_format_integer(self, writer):
        """Un intero viene convertito e formattato."""
        result = writer._format_param(4, 1, " voices")
        assert result == "4.0 voices"

    def test_format_parameter_extracts_value(self, writer):
        """Un Parameter viene unwrappato tramite _value."""
        mock_param = _make_mock_parameter_instance(value=0.03)
        result = writer._format_param(mock_param, 1000, "ms")
        assert result == "30.0ms"

    def test_format_parameter_with_envelope_value(self, writer):
        """Un Parameter con Envelope._value restituisce 'dynamic'."""
        mock_env = make_real_envelope()
        mock_param = _make_mock_parameter_instance(value=mock_env)
        result = writer._format_param(mock_param)
        assert result == "dynamic (envelope)"

    def test_format_envelope_directly(self, writer):
        """Un Envelope diretto restituisce 'dynamic (envelope)'."""
        mock_env = make_real_envelope()
        result = writer._format_param(mock_env)
        assert result == "dynamic (envelope)"

    def test_format_zero_value(self, writer):
        """Zero viene formattato correttamente."""
        result = writer._format_param(0.0, 1, "ms")
        assert result == "0.0ms"

    def test_format_negative_value(self, writer):
        """Valori negativi vengono formattati correttamente."""
        result = writer._format_param(-6.0, 1, "dB")
        assert result == "-6.0dB"

    def test_format_string_fallback(self, writer):
        """Una stringa non convertibile viene restituita as-is."""
        result = writer._format_param("custom_mode")
        assert result == "custom_mode"

    def test_format_large_multiplier(self, writer):
        """Moltiplicatore grande funziona correttamente."""
        result = writer._format_param(0.001, 1000, "ms")
        assert result == "1.0ms"

    def test_format_parameter_with_none_value(self, writer):
        """Parameter con _value=None restituisce 'N/A'."""
        mock_param = _make_mock_parameter_instance(value=None)
        # Dopo estrazione _value, param diventa None
        result = writer._format_param(mock_param)
        assert result == "N/A"


# =============================================================================
# 11. TEST _print_generation_summary
# =============================================================================

class TestPrintGenerationSummary:
    """Test per _print_generation_summary."""

    def test_summary_prints_filepath(self, writer, capsys):
        """Il riepilogo stampa il percorso del file."""
        writer._print_generation_summary('output.sco', [], [])
        captured = capsys.readouterr()

        assert "output.sco" in captured.out

    def test_summary_prints_table_count(self, writer, capsys):
        """Il riepilogo stampa il numero di function tables."""
        writer._print_generation_summary('out.sco', [], [])
        captured = capsys.readouterr()

        assert "3 function tables" in captured.out

    def test_summary_prints_stream_count(self, writer, capsys, sample_stream):
        """Il riepilogo stampa il numero di streams."""
        writer._print_generation_summary('out.sco', [sample_stream], [])
        captured = capsys.readouterr()

        assert "1 streams granulari" in captured.out

    def test_summary_prints_grain_total(self, writer, capsys):
        """Il riepilogo stampa il totale grani."""
        grains = [make_mock_grain() for _ in range(10)]
        stream = make_mock_stream(voices=[grains])

        writer._print_generation_summary('out.sco', [stream], [])
        captured = capsys.readouterr()

        assert "10 grani totali" in captured.out

    def test_summary_prints_cartridges_count(self, writer, capsys, sample_cartridge):
        """Il riepilogo stampa il numero di cartridges."""
        writer._print_generation_summary('out.sco', [], [sample_cartridge])
        captured = capsys.readouterr()

        assert "1 cartridges tape recorder" in captured.out

    def test_summary_no_streams_section_if_empty(self, writer, capsys):
        """Senza streams, non stampa la sezione streams."""
        writer._print_generation_summary('out.sco', [], [])
        captured = capsys.readouterr()

        assert "streams granulari" not in captured.out
        assert "grani totali" not in captured.out

    def test_summary_no_cartridges_section_if_empty(self, writer, capsys):
        """Senza cartridges, non stampa la sezione cartridges."""
        writer._print_generation_summary('out.sco', [], [])
        captured = capsys.readouterr()

        assert "cartridges tape recorder" not in captured.out

    def test_summary_multiple_streams_grain_total(self, writer, capsys):
        """Il totale grani somma correttamente su piu' streams."""
        s1 = make_mock_stream(voices=[[make_mock_grain() for _ in range(5)]])
        s2 = make_mock_stream(voices=[[make_mock_grain() for _ in range(8)]])

        writer._print_generation_summary('out.sco', [s1, s2], [])
        captured = capsys.readouterr()

        assert "2 streams granulari" in captured.out
        assert "13 grani totali" in captured.out


# =============================================================================
# 12. TEST write_score (ORCHESTRAZIONE COMPLETA)
# =============================================================================

class TestWriteScore:
    """Test per write_score (metodo pubblico principale)."""

    def test_write_score_creates_file(self, writer, tmp_path, sample_stream, sample_cartridge):
        """write_score crea effettivamente un file."""
        filepath = str(tmp_path / 'test_output.sco')

        writer.write_score(filepath, [sample_stream], [sample_cartridge])

        assert os.path.exists(filepath)

    def test_write_score_file_not_empty(self, writer, tmp_path, sample_stream):
        """Il file generato non e' vuoto."""
        filepath = str(tmp_path / 'test_output.sco')

        writer.write_score(filepath, [sample_stream], [])

        with open(filepath, 'r') as f:
            content = f.read()
        assert len(content) > 0

    def test_write_score_structure_order(self, writer, tmp_path, sample_stream, sample_cartridge):
        """Il file ha la struttura corretta: header -> ftables -> events -> footer."""
        filepath = str(tmp_path / 'test_output.sco')

        writer.write_score(filepath, [sample_stream], [sample_cartridge], yaml_source='test.yml')

        with open(filepath, 'r') as f:
            content = f.read()

        # Verifica ordine sezioni
        header_pos = content.index("CSOUND SCORE")
        # ftable_manager.write_to_file e' stato chiamato (mock)
        writer.ftable_manager.write_to_file.assert_called_once()
        gran_pos = content.index("GRANULAR STREAMS")
        tape_pos = content.index("TAPE RECORDER")
        footer_pos = content.index("End of score")

        assert header_pos < gran_pos < tape_pos < footer_pos

    def test_write_score_calls_ftable_write(self, writer, tmp_path, sample_stream):
        """write_score delega la scrittura ftables a FtableManager."""
        filepath = str(tmp_path / 'test_output.sco')

        writer.write_score(filepath, [sample_stream], [])

        writer.ftable_manager.write_to_file.assert_called_once()

    def test_write_score_calls_print_summary(self, writer, tmp_path, sample_stream, capsys):
        """write_score stampa il riepilogo generazione."""
        filepath = str(tmp_path / 'test_output.sco')

        writer.write_score(filepath, [sample_stream], [])

        captured = capsys.readouterr()
        assert "Score generato" in captured.out

    def test_write_score_with_yaml_source(self, writer, tmp_path, sample_stream):
        """write_score include yaml_source nell'header."""
        filepath = str(tmp_path / 'test_output.sco')

        writer.write_score(filepath, [sample_stream], [], yaml_source='my_config.yml')

        with open(filepath, 'r') as f:
            content = f.read()
        assert "; Generated from: my_config.yml" in content

    def test_write_score_without_yaml_source(self, writer, tmp_path, sample_stream):
        """write_score senza yaml_source non include Generated from."""
        filepath = str(tmp_path / 'test_output.sco')

        writer.write_score(filepath, [sample_stream], [])

        with open(filepath, 'r') as f:
            content = f.read()
        assert "Generated from" not in content

    def test_write_score_empty_streams_and_cartridges(self, writer, tmp_path):
        """write_score con liste vuote genera solo header + footer."""
        filepath = str(tmp_path / 'test_output.sco')

        writer.write_score(filepath, [], [])

        with open(filepath, 'r') as f:
            content = f.read()

        assert "CSOUND SCORE" in content
        assert "End of score" in content
        assert "e\n" in content
        assert "GRANULAR STREAMS" not in content
        assert "TAPE RECORDER" not in content

    def test_write_score_ends_with_e_statement(self, writer, tmp_path, sample_stream):
        """Lo score termina sempre con lo statement 'e' di Csound."""
        filepath = str(tmp_path / 'test_output.sco')

        writer.write_score(filepath, [sample_stream], [])

        with open(filepath, 'r') as f:
            content = f.read()
        assert content.strip().endswith("e")


# =============================================================================
# 13. TEST INTEGRAZIONE - SCORE COMPLETO
# =============================================================================

class TestScoreIntegration:
    """Test di integrazione end-to-end sulla struttura del file generato."""

    def test_full_score_with_multiple_streams_and_cartridges(self, writer, tmp_path):
        """Score completo con piu' stream e cartridges."""
        s1 = make_mock_stream(stream_id='cloud_01', voices=[
            [make_mock_grain(i * 0.05) for i in range(10)],
            [make_mock_grain(i * 0.05 + 0.01) for i in range(8)],
        ])
        s2 = make_mock_stream(stream_id='cloud_02', voices=[
            [make_mock_grain(i * 0.1) for i in range(5)],
        ])
        t1 = make_mock_cartridge(cartridge_id='tape_A')
        t2 = make_mock_cartridge(cartridge_id='tape_B')

        filepath = str(tmp_path / 'full_score.sco')
        writer.write_score(filepath, [s1, s2], [t1, t2], yaml_source='composition.yml')

        with open(filepath, 'r') as f:
            content = f.read()

        # Header
        assert "CSOUND SCORE" in content
        assert "Generated from: composition.yml" in content

        # Stream sections
        assert "; Stream: cloud_01" in content
        assert "; Stream: cloud_02" in content

        # cartridge sections
        assert "; Cartridge: tape_A" in content
        assert "; Cartridge: tape_B" in content

        # Footer
        assert "End of score" in content
        assert content.strip().endswith("e")

    def test_score_grain_lines_are_valid_csound(self, writer, tmp_path):
        """Verifica che le linee grano abbiano il formato Csound valido."""
        grain = make_mock_grain(
            onset=1.5,
            duration=0.05,
            score_line='i "Grain" 1.500000 0.050000 2.300000 1.000000 -6.00 0.500 1 2\n'
        )
        stream = make_mock_stream(voices=[[grain]])
        filepath = str(tmp_path / 'valid.sco')

        writer.write_score(filepath, [stream], [])

        with open(filepath, 'r') as f:
            content = f.read()

        # Ogni riga 'i "Grain"' ha il formato corretto
        for line in content.split('\n'):
            if line.startswith('i "Grain"'):
                parts = line.split()
                assert len(parts) == 10  # i "Grain" + 8 p-fields

    def test_score_cartridge_lines_are_valid_csound(self, writer, tmp_path):
        """Verifica che le linee cartridge abbiano il formato Csound valido."""
        cartridge = make_mock_cartridge(
            score_line='i "TapeRecorder" 0.000000 5.000000 0.000000 1.000000 0.00 0.500 0 0.000000 -1.000000 1\n'
        )
        filepath = str(tmp_path / 'valid.sco')

        writer.write_score(filepath, [], [cartridge])

        with open(filepath, 'r') as f:
            content = f.read()

        for line in content.split('\n'):
            if line.startswith('i "TapeRecorder"'):
                parts = line.split()
                assert len(parts) == 12  # i "TapeRecorder" + 10 p-fields


# =============================================================================
# 14. TEST EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Test per casi limite e robustezza."""

    def test_stream_with_all_empty_voices(self, writer, string_file):
        """Stream con tutte le voice vuote: nessun grano scritto."""
        stream = make_mock_stream(voices=[[], [], []])
        writer._write_stream_section(string_file, stream)
        content = string_file.getvalue()

        assert 'i "Grain"' not in content
        # Ma l'header stream e' comunque presente
        assert "; Stream:" in content

    def test_stream_with_single_grain(self, writer, string_file):
        """Stream con un singolo grano."""
        grain = make_mock_grain(0.0, 0.05)
        stream = make_mock_stream(voices=[[grain]])

        writer._write_stream_section(string_file, stream)
        content = string_file.getvalue()

        assert "1 grains" in content
        grain.to_score_line.assert_called_once()

    def test_stream_with_many_voices(self, writer, string_file):
        """Stream con molte voice (simula max_voices alto)."""
        voices = [[make_mock_grain()] for _ in range(20)]
        stream = make_mock_stream(num_voices=20, voices=voices)

        writer._write_stream_section(string_file, stream)
        content = string_file.getvalue()

        # Verifica che tutte le voice siano scritte
        for i in range(20):
            assert f"Voice {i}" in content

    def test_format_param_with_very_small_float(self, writer):
        """_format_param con float molto piccolo."""
        result = writer._format_param(0.0001, 1000, "ms")
        assert "0.1ms" in result

    def test_format_param_with_very_large_float(self, writer):
        """_format_param con float molto grande."""
        result = writer._format_param(1000.0, 1, " g/s")
        assert "1000.0 g/s" in result

    def test_write_score_overwrites_existing_file(self, writer, tmp_path, sample_stream):
        """write_score sovrascrive un file esistente."""
        filepath = str(tmp_path / 'overwrite.sco')

        # Crea file pre-esistente
        with open(filepath, 'w') as f:
            f.write("old content\n")

        writer.write_score(filepath, [sample_stream], [])

        with open(filepath, 'r') as f:
            content = f.read()

        assert "old content" not in content
        assert "CSOUND SCORE" in content

    def test_write_score_with_unicode_yaml_path(self, writer, tmp_path, sample_stream):
        """write_score gestisce path YAML con caratteri unicode."""
        filepath = str(tmp_path / 'test.sco')

        writer.write_score(filepath, [sample_stream], [],
                          yaml_source='composizioni/nuvola_sonora.yml')

        with open(filepath, 'r') as f:
            content = f.read()

        assert "composizioni/nuvola_sonora.yml" in content


# =============================================================================
# 15. TEST _format_param PARAMETRIZZATI
# =============================================================================

class TestFormatParamParametrized:
    """Test parametrizzati per copertura sistematica di _format_param."""

    @pytest.mark.parametrize("param,mult,unit,expected", [
        (0.05, 1000, "ms", "50.0ms"),
        (10.0, 1, " g/s", "10.0 g/s"),
        (0.7, 1.0, "", "0.7"),
        (4, 1, " voices", "4.0 voices"),
        (-12.0, 1, "dB", "-12.0dB"),
        (0.0, 1, "Hz", "0.0Hz"),
        (0.001, 1000, "ms", "1.0ms"),
        (100.0, 1, "", "100.0"),
    ])
    def test_format_numeric_values(self, writer, param, mult, unit, expected):
        """Valori numerici formattati con moltiplicatore e unita'."""
        result = writer._format_param(param, mult, unit)
        assert result == expected

    @pytest.mark.parametrize("param,expected", [
        (None, "N/A"),
        ("custom", "custom"),
    ])
    def test_format_special_values(self, writer, param, expected):
        """Valori speciali (None, stringhe)."""
        result = writer._format_param(param)
        assert result == expected


# =============================================================================
# 16. TEST _write_stream_section CON onset_offset (RED - fix problema 1)
# =============================================================================

class TestWriteStreamSectionOnsetOffset:
    """Test per _write_stream_section(onset_offset=...) - onset relativo STEMS."""

    def test_default_onset_offset_zero_calls_grain_without_offset(
        self, writer, string_file
    ):
        """onset_offset=0.0 (default): grain.to_score_line chiamato con onset_offset=0.0."""
        grain = make_mock_grain(onset=5.0)
        stream = make_mock_stream(voices=[[grain]])

        writer._write_stream_section(string_file, stream)

        grain.to_score_line.assert_called_once_with(onset_offset=0.0)

    def test_onset_offset_passed_to_grain_to_score_line(self, writer, string_file):
        """onset_offset=5.0 viene passato a ogni grain.to_score_line."""
        grain_a = make_mock_grain(onset=5.0)
        grain_b = make_mock_grain(onset=5.1)
        stream = make_mock_stream(voices=[[grain_a, grain_b]])

        writer._write_stream_section(string_file, stream, onset_offset=5.0)

        grain_a.to_score_line.assert_called_once_with(onset_offset=5.0)
        grain_b.to_score_line.assert_called_once_with(onset_offset=5.0)

    def test_onset_offset_applied_to_all_voices(self, writer, string_file):
        """onset_offset viene passato ai grani di tutte le voices."""
        grain_v0 = make_mock_grain(onset=3.0)
        grain_v1 = make_mock_grain(onset=3.05)
        stream = make_mock_stream(voices=[[grain_v0], [grain_v1]])

        writer._write_stream_section(string_file, stream, onset_offset=3.0)

        grain_v0.to_score_line.assert_called_once_with(onset_offset=3.0)
        grain_v1.to_score_line.assert_called_once_with(onset_offset=3.0)


# =============================================================================
# 17. TEST write_score CON per_stream=True (RED - fix problema 1)
# =============================================================================

class TestWriteScorePerStream:
    """Test per write_score(per_stream=True) - passa onset_offset=stream.onset."""

    def test_write_score_per_stream_false_by_default(self, writer, tmp_path):
        """per_stream=False e' il default: onset_offset=0.0 per ogni stream."""
        stream = make_mock_stream(voices=[[make_mock_grain(onset=0.0)]])
        stream.onset = 0.0

        filepath = str(tmp_path / 'test.sco')
        writer.write_score(filepath, [stream], [])

        # Nessuna eccezione, il file viene scritto
        assert os.path.exists(filepath)

    def test_write_score_per_stream_true_uses_stream_onset_as_offset(
        self, writer, tmp_path
    ):
        """per_stream=True: _write_stream_section riceve onset_offset=stream.onset."""
        grain = make_mock_grain(onset=5.0)
        stream = make_mock_stream(voices=[[grain]])
        stream.onset = 5.0

        filepath = str(tmp_path / 'test_per_stream.sco')
        writer.write_score(filepath, [stream], [], per_stream=True)

        grain.to_score_line.assert_called_once_with(onset_offset=5.0)

    def test_write_score_per_stream_true_multiple_streams_each_uses_own_onset(
        self, writer, tmp_path
    ):
        """Con piu' stream e per_stream=True, ogni stream usa il proprio onset."""
        grain_a = make_mock_grain(onset=3.0)
        grain_b = make_mock_grain(onset=7.0)
        stream_a = make_mock_stream(stream_id='s1', voices=[[grain_a]])
        stream_a.onset = 3.0
        stream_b = make_mock_stream(stream_id='s2', voices=[[grain_b]])
        stream_b.onset = 7.0

        filepath = str(tmp_path / 'multi.sco')
        writer.write_score(filepath, [stream_a, stream_b], [], per_stream=True)

        grain_a.to_score_line.assert_called_once_with(onset_offset=3.0)
        grain_b.to_score_line.assert_called_once_with(onset_offset=7.0)

    def test_write_score_per_stream_false_uses_zero_offset(self, writer, tmp_path):
        """per_stream=False: onset_offset=0.0 (onset assoluto, comportamento pre-fix)."""
        grain = make_mock_grain(onset=5.0)
        stream = make_mock_stream(voices=[[grain]])
        stream.onset = 5.0

        filepath = str(tmp_path / 'abs.sco')
        writer.write_score(filepath, [stream], [], per_stream=False)

        grain.to_score_line.assert_called_once_with(onset_offset=0.0)