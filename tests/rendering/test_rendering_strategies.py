# tests/rendering/test_rendering_strategies.py
"""
TDD suite per Strategy Composition Architecture (OCP-compliant).

Nuove astrazioni:
1. NamingStrategy: genera path output da base_path + streams + mode
2. RenderMode: strategia per stems/mix/per-voice
3. RenderingEngine: facade che coordina renderer + naming + mode

Coverage:
- TestNamingStrategy: DefaultNamingStrategy genera path corretti
- TestRenderMode: StemsRenderMode e MixRenderMode funzionano
- TestRenderingEngine: coordina componenti correttamente
- TestOCPCompliance: estensioni non richiedono modifiche
"""

import pytest
from unittest.mock import MagicMock, call
from typing import List


# =============================================================================
# MOCKS
# =============================================================================

def make_mock_stream(stream_id='s1', onset=0.0, duration=1.0, voices=None):
    """Mock Stream minimale."""
    stream = MagicMock()
    stream.stream_id = stream_id
    stream.onset = onset
    stream.duration = duration
    stream.voices = voices or [[]]
    return stream


def make_mock_renderer():
    """Mock AudioRenderer atomico.

    render_single_stream rispetta il contratto ABC (ritorna il path
    prodotto); render_streams replica il default concreto dell'ABC
    (loop su render_single_stream), cosi' i test sul loop restano validi.
    """
    renderer = MagicMock()
    renderer.render_single_stream = MagicMock(side_effect=lambda stream, path: path)
    renderer.render_merged_streams = MagicMock(return_value='/out/mix.aif')
    renderer.render_streams = MagicMock(
        side_effect=lambda pairs: [
            renderer.render_single_stream(stream, path) for stream, path in pairs
        ]
    )
    return renderer


# =============================================================================
# 1. TEST NAMING STRATEGY
# =============================================================================

class TestDefaultNamingStrategy:
    """Test per DefaultNamingStrategy."""

    def test_generates_stems_paths(self):
        """Mode 'stems': genera un path per stream con suffisso __streamid."""
        from pge.rendering.naming_strategy import DefaultNamingStrategy

        naming = DefaultNamingStrategy()
        streams = [
            make_mock_stream('stream1'),
            make_mock_stream('stream2'),
        ]

        paths = naming.generate_paths('/out/base.aif', streams, mode='stems')

        assert len(paths) == 2
        assert paths[0] == (streams[0], '/out/base__stream1.aif')
        assert paths[1] == (streams[1], '/out/base__stream2.aif')

    def test_generates_mix_path(self):
        """Mode 'mix': genera un solo path per tutti gli stream."""
        from pge.rendering.naming_strategy import DefaultNamingStrategy

        naming = DefaultNamingStrategy()
        streams = [
            make_mock_stream('s1'),
            make_mock_stream('s2'),
            make_mock_stream('s3'),
        ]

        paths = naming.generate_paths('/out/composition.aif', streams, mode='mix')

        assert len(paths) == 1
        assert paths[0][0] == streams  # tutti gli stream
        assert paths[0][1] == '/out/composition.aif'

    def test_handles_path_with_extension(self):
        """Gestisce correttamente path con estensione."""
        from pge.rendering.naming_strategy import DefaultNamingStrategy

        naming = DefaultNamingStrategy()
        streams = [make_mock_stream('test')]

        paths = naming.generate_paths('/dir/file.aif', streams, mode='stems')

        assert paths[0][1] == '/dir/file__test.aif'

    def test_handles_path_without_extension(self):
        """Gestisce correttamente path senza estensione."""
        from pge.rendering.naming_strategy import DefaultNamingStrategy

        naming = DefaultNamingStrategy()
        streams = [make_mock_stream('test')]

        paths = naming.generate_paths('/dir/file', streams, mode='stems')

        assert paths[0][1] == '/dir/file__test.aif'

    def test_invalid_mode_raises_error(self):
        """Mode non valido solleva ValueError."""
        from pge.rendering.naming_strategy import DefaultNamingStrategy

        naming = DefaultNamingStrategy()
        streams = [make_mock_stream()]

        with pytest.raises(ValueError, match="naming"):
            naming.generate_paths('/out/base.aif', streams, mode='invalid')

    def test_stems_wav_extension(self):
        """ext='.wav' genera path con estensione .wav."""
        from pge.rendering.naming_strategy import DefaultNamingStrategy

        naming = DefaultNamingStrategy(ext='.wav')
        streams = [make_mock_stream('s1'), make_mock_stream('s2')]

        paths = naming.generate_paths('/out/base.aif', streams, mode='stems')

        assert paths[0][1] == '/out/base__s1.wav'
        assert paths[1][1] == '/out/base__s2.wav'

    def test_stems_flac_extension(self):
        """ext='.flac' genera path con estensione .flac."""
        from pge.rendering.naming_strategy import DefaultNamingStrategy

        naming = DefaultNamingStrategy(ext='.flac')
        streams = [make_mock_stream('s1')]

        paths = naming.generate_paths('/out/base.aif', streams, mode='stems')

        assert paths[0][1] == '/out/base__s1.flac'

    def test_default_extension_unchanged(self):
        """Senza parametri ext, default rimane .aif."""
        from pge.rendering.naming_strategy import DefaultNamingStrategy

        naming = DefaultNamingStrategy()
        streams = [make_mock_stream('s1')]

        paths = naming.generate_paths('/out/base.aif', streams, mode='stems')

        assert paths[0][1] == '/out/base__s1.aif'

    def test_stems_uses_double_underscore_separator(self):
        """STEMS mode: separatore tra basename e stream_id e' '__' (issue #56).

        Il doppio underscore garantisce parsing inverso non ambiguo:
        stem.split('__') restituisce sempre ['basename', 'stream_id']
        anche se basename o stream_id contengono singoli underscores.
        """
        from pge.rendering.naming_strategy import DefaultNamingStrategy

        naming = DefaultNamingStrategy()
        streams = [make_mock_stream('s1')]

        paths = naming.generate_paths('/out/PGE_test.aif', streams, mode='stems')

        assert paths[0][1] == '/out/PGE_test__s1.aif'

        stem = paths[0][1].split('/')[-1].replace('.aif', '')
        basename, sid = stem.split('__')
        assert basename == 'PGE_test'
        assert sid == 's1'


# =============================================================================
# 2. TEST RENDER MODE - STEMS
# =============================================================================

class TestStemsRenderMode:
    """Test per StemsRenderMode."""

    def test_calls_render_single_stream_for_each_stream(self):
        """Chiama render_single_stream per ogni stream."""
        from pge.rendering.render_mode import StemsRenderMode
        from pge.rendering.naming_strategy import DefaultNamingStrategy

        mode = StemsRenderMode()
        renderer = make_mock_renderer()
        naming = DefaultNamingStrategy()

        streams = [
            make_mock_stream('s1'),
            make_mock_stream('s2'),
        ]

        result = mode.execute(renderer, naming, streams, '/out/base.aif')

        assert renderer.render_single_stream.call_count == 2
        renderer.render_single_stream.assert_any_call(streams[0], '/out/base__s1.aif')
        renderer.render_single_stream.assert_any_call(streams[1], '/out/base__s2.aif')

    def test_returns_list_of_generated_paths(self):
        """Ritorna lista di path generati."""
        from pge.rendering.render_mode import StemsRenderMode
        from pge.rendering.naming_strategy import DefaultNamingStrategy

        mode = StemsRenderMode()
        renderer = make_mock_renderer()
        naming = DefaultNamingStrategy()

        streams = [make_mock_stream('s1'), make_mock_stream('s2')]

        result = mode.execute(renderer, naming, streams, '/out/base.aif')

        assert len(result) == 2
        assert '/out/base__s1.aif' in result
        assert '/out/base__s2.aif' in result

    def test_works_with_single_stream(self):
        """Funziona con un solo stream."""
        from pge.rendering.render_mode import StemsRenderMode
        from pge.rendering.naming_strategy import DefaultNamingStrategy

        mode = StemsRenderMode()
        renderer = make_mock_renderer()
        naming = DefaultNamingStrategy()

        streams = [make_mock_stream('solo')]

        result = mode.execute(renderer, naming, streams, '/out/base.aif')

        assert len(result) == 1
        assert result[0] == '/out/base__solo.aif'

    def test_delegates_loop_to_render_streams(self):
        """execute delega il loop a renderer.render_streams con le coppie
        (stream, path) del naming: il mode decide COSA (stems), il renderer
        decide COME (seriale o parallelo)."""
        from pge.rendering.render_mode import StemsRenderMode
        from pge.rendering.naming_strategy import DefaultNamingStrategy

        mode = StemsRenderMode()
        renderer = make_mock_renderer()
        naming = DefaultNamingStrategy()

        streams = [make_mock_stream('s1'), make_mock_stream('s2')]

        result = mode.execute(renderer, naming, streams, '/out/base.aif')

        renderer.render_streams.assert_called_once()
        (pairs,) = renderer.render_streams.call_args.args
        assert pairs == [
            (streams[0], '/out/base__s1.aif'),
            (streams[1], '/out/base__s2.aif'),
        ]
        assert result == ['/out/base__s1.aif', '/out/base__s2.aif']


# =============================================================================
# 3. TEST RENDER MODE - MIX
# =============================================================================

class TestMixRenderMode:
    """Test per MixRenderMode."""

    def test_calls_render_merged_streams_once(self):
        """Chiama render_merged_streams una sola volta con tutti gli stream."""
        from pge.rendering.render_mode import MixRenderMode
        from pge.rendering.naming_strategy import DefaultNamingStrategy

        mode = MixRenderMode()
        renderer = make_mock_renderer()
        naming = DefaultNamingStrategy()

        streams = [
            make_mock_stream('s1'),
            make_mock_stream('s2'),
            make_mock_stream('s3'),
        ]

        result = mode.execute(renderer, naming, streams, '/out/mix.aif')

        renderer.render_merged_streams.assert_called_once_with(streams, '/out/mix.aif')

    def test_returns_single_path(self):
        """Ritorna una lista con un solo path."""
        from pge.rendering.render_mode import MixRenderMode
        from pge.rendering.naming_strategy import DefaultNamingStrategy

        mode = MixRenderMode()
        renderer = make_mock_renderer()
        naming = DefaultNamingStrategy()

        streams = [make_mock_stream('s1'), make_mock_stream('s2')]

        result = mode.execute(renderer, naming, streams, '/out/composition.aif')

        assert len(result) == 1
        assert result[0] == '/out/composition.aif'

    def test_does_not_call_render_single_stream(self):
        """NON chiama render_single_stream (solo render_merged_streams)."""
        from pge.rendering.render_mode import MixRenderMode
        from pge.rendering.naming_strategy import DefaultNamingStrategy

        mode = MixRenderMode()
        renderer = make_mock_renderer()
        naming = DefaultNamingStrategy()

        streams = [make_mock_stream('s1')]

        mode.execute(renderer, naming, streams, '/out/mix.aif')

        renderer.render_single_stream.assert_not_called()


# =============================================================================
# 4. TEST RENDERING ENGINE
# =============================================================================

class TestRenderingEngine:
    """Test per RenderingEngine (Facade)."""

    def test_creates_with_renderer(self):
        """RenderingEngine si crea con un renderer."""
        from pge.rendering.rendering_engine import RenderingEngine

        renderer = make_mock_renderer()
        engine = RenderingEngine(renderer)

        assert engine.renderer is renderer

    def test_creates_with_default_naming_strategy(self):
        """Usa DefaultNamingStrategy se non specificata."""
        from pge.rendering.rendering_engine import RenderingEngine
        from pge.rendering.naming_strategy import DefaultNamingStrategy

        renderer = make_mock_renderer()
        engine = RenderingEngine(renderer)

        assert isinstance(engine.naming, DefaultNamingStrategy)

    def test_accepts_custom_naming_strategy(self):
        """Accetta naming strategy custom."""
        from pge.rendering.rendering_engine import RenderingEngine

        renderer = make_mock_renderer()
        custom_naming = MagicMock()

        engine = RenderingEngine(renderer, naming_strategy=custom_naming)

        assert engine.naming is custom_naming

    def test_render_delegates_to_mode(self):
        """render() delega l'esecuzione al RenderMode."""
        from pge.rendering.rendering_engine import RenderingEngine

        renderer = make_mock_renderer()
        engine = RenderingEngine(renderer)

        mode = MagicMock()
        mode.execute = MagicMock(return_value=['/out/test.aif'])

        streams = [make_mock_stream()]
        result = engine.render(streams, '/out/base.aif', mode)

        mode.execute.assert_called_once_with(
            renderer=renderer,
            naming=engine.naming,
            streams=streams,
            output_path='/out/base.aif'
        )

    def test_render_returns_mode_result(self):
        """render() ritorna il risultato del mode."""
        from pge.rendering.rendering_engine import RenderingEngine

        renderer = make_mock_renderer()
        engine = RenderingEngine(renderer)

        mode = MagicMock()
        mode.execute = MagicMock(return_value=['/a.aif', '/b.aif'])

        streams = [make_mock_stream()]
        result = engine.render(streams, '/out/base.aif', mode)

        assert result == ['/a.aif', '/b.aif']


# =============================================================================
# 5. TEST OCP COMPLIANCE
# =============================================================================

class TestOCPCompliance:
    """Test che verificano l'aderenza all'Open/Closed Principle."""

    def test_custom_naming_strategy_works(self):
        """Una custom NamingStrategy funziona senza modifiche al codice."""
        from pge.rendering.rendering_engine import RenderingEngine
        from pge.rendering.render_mode import StemsRenderMode
        from pge.rendering.naming_strategy import NamingStrategy

        # Custom naming: usa trattino invece di underscore
        class DashNamingStrategy(NamingStrategy):
            def generate_paths(self, base_path, streams, mode):
                import os
                base = os.path.splitext(base_path)[0]
                if mode == 'stems':
                    return [(s, f"{base}-{s.stream_id}.aif") for s in streams]
                else:
                    return [(streams, base_path)]

        renderer = make_mock_renderer()
        custom_naming = DashNamingStrategy()
        engine = RenderingEngine(renderer, naming_strategy=custom_naming)

        mode = StemsRenderMode()
        streams = [make_mock_stream('test')]

        result = engine.render(streams, '/out/base.aif', mode)

        # Verifica che usi trattino
        renderer.render_single_stream.assert_called_once_with(streams[0], '/out/base-test.aif')

    def test_new_render_mode_works(self):
        """Un nuovo RenderMode funziona senza modifiche al codice."""
        from pge.rendering.rendering_engine import RenderingEngine
        from pge.rendering.render_mode import RenderMode
        from pge.rendering.naming_strategy import DefaultNamingStrategy

        # Custom mode: renderizza solo il primo stream
        class FirstStreamOnlyMode(RenderMode):
            def execute(self, renderer, naming, streams, output_path):
                first_stream = streams[0]
                renderer.render_single_stream(first_stream, output_path)
                return [output_path]

        renderer = make_mock_renderer()
        engine = RenderingEngine(renderer)

        mode = FirstStreamOnlyMode()
        streams = [make_mock_stream('first'), make_mock_stream('second')]

        result = engine.render(streams, '/out/test.aif', mode)

        # Verifica che renderizzi solo il primo
        renderer.render_single_stream.assert_called_once_with(streams[0], '/out/test.aif')
        assert len(result) == 1
