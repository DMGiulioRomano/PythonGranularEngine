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
    """Mock AudioRenderer atomico."""
    renderer = MagicMock()
    renderer.render_single_stream = MagicMock(return_value='/out/s1.aif')
    renderer.render_merged_streams = MagicMock(return_value='/out/mix.aif')
    return renderer


# =============================================================================
# 1. TEST NAMING STRATEGY
# =============================================================================

class TestDefaultNamingStrategy:
    """Test per DefaultNamingStrategy."""

    def test_generates_stems_paths(self):
        """Mode 'stems': genera un path per stream con suffisso _streamid."""
        from rendering.naming_strategy import DefaultNamingStrategy

        naming = DefaultNamingStrategy()
        streams = [
            make_mock_stream('stream1'),
            make_mock_stream('stream2'),
        ]

        paths = naming.generate_paths('/out/base.aif', streams, mode='stems')

        assert len(paths) == 2
        assert paths[0] == (streams[0], '/out/base_stream1.aif')
        assert paths[1] == (streams[1], '/out/base_stream2.aif')

    def test_generates_mix_path(self):
        """Mode 'mix': genera un solo path per tutti gli stream."""
        from rendering.naming_strategy import DefaultNamingStrategy

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
        from rendering.naming_strategy import DefaultNamingStrategy

        naming = DefaultNamingStrategy()
        streams = [make_mock_stream('test')]

        paths = naming.generate_paths('/dir/file.aif', streams, mode='stems')

        assert paths[0][1] == '/dir/file_test.aif'

    def test_handles_path_without_extension(self):
        """Gestisce correttamente path senza estensione."""
        from rendering.naming_strategy import DefaultNamingStrategy

        naming = DefaultNamingStrategy()
        streams = [make_mock_stream('test')]

        paths = naming.generate_paths('/dir/file', streams, mode='stems')

        assert paths[0][1] == '/dir/file_test.aif'

    def test_invalid_mode_raises_error(self):
        """Mode non valido solleva ValueError."""
        from rendering.naming_strategy import DefaultNamingStrategy

        naming = DefaultNamingStrategy()
        streams = [make_mock_stream()]

        with pytest.raises(ValueError, match="Mode 'invalid' not supported"):
            naming.generate_paths('/out/base.aif', streams, mode='invalid')


# =============================================================================
# 2. TEST RENDER MODE - STEMS
# =============================================================================

class TestStemsRenderMode:
    """Test per StemsRenderMode."""

    def test_calls_render_single_stream_for_each_stream(self):
        """Chiama render_single_stream per ogni stream."""
        from rendering.render_mode import StemsRenderMode
        from rendering.naming_strategy import DefaultNamingStrategy

        mode = StemsRenderMode()
        renderer = make_mock_renderer()
        naming = DefaultNamingStrategy()

        streams = [
            make_mock_stream('s1'),
            make_mock_stream('s2'),
        ]

        result = mode.execute(renderer, naming, streams, '/out/base.aif')

        assert renderer.render_single_stream.call_count == 2
        renderer.render_single_stream.assert_any_call(streams[0], '/out/base_s1.aif')
        renderer.render_single_stream.assert_any_call(streams[1], '/out/base_s2.aif')

    def test_returns_list_of_generated_paths(self):
        """Ritorna lista di path generati."""
        from rendering.render_mode import StemsRenderMode
        from rendering.naming_strategy import DefaultNamingStrategy

        mode = StemsRenderMode()
        renderer = make_mock_renderer()
        naming = DefaultNamingStrategy()

        streams = [make_mock_stream('s1'), make_mock_stream('s2')]

        result = mode.execute(renderer, naming, streams, '/out/base.aif')

        assert len(result) == 2
        assert '/out/base_s1.aif' in result
        assert '/out/base_s2.aif' in result

    def test_works_with_single_stream(self):
        """Funziona con un solo stream."""
        from rendering.render_mode import StemsRenderMode
        from rendering.naming_strategy import DefaultNamingStrategy

        mode = StemsRenderMode()
        renderer = make_mock_renderer()
        naming = DefaultNamingStrategy()

        streams = [make_mock_stream('solo')]

        result = mode.execute(renderer, naming, streams, '/out/base.aif')

        assert len(result) == 1
        assert result[0] == '/out/base_solo.aif'


# =============================================================================
# 3. TEST RENDER MODE - MIX
# =============================================================================

class TestMixRenderMode:
    """Test per MixRenderMode."""

    def test_calls_render_merged_streams_once(self):
        """Chiama render_merged_streams una sola volta con tutti gli stream."""
        from rendering.render_mode import MixRenderMode
        from rendering.naming_strategy import DefaultNamingStrategy

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
        from rendering.render_mode import MixRenderMode
        from rendering.naming_strategy import DefaultNamingStrategy

        mode = MixRenderMode()
        renderer = make_mock_renderer()
        naming = DefaultNamingStrategy()

        streams = [make_mock_stream('s1'), make_mock_stream('s2')]

        result = mode.execute(renderer, naming, streams, '/out/composition.aif')

        assert len(result) == 1
        assert result[0] == '/out/composition.aif'

    def test_does_not_call_render_single_stream(self):
        """NON chiama render_single_stream (solo render_merged_streams)."""
        from rendering.render_mode import MixRenderMode
        from rendering.naming_strategy import DefaultNamingStrategy

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
        from rendering.rendering_engine import RenderingEngine

        renderer = make_mock_renderer()
        engine = RenderingEngine(renderer)

        assert engine.renderer is renderer

    def test_creates_with_default_naming_strategy(self):
        """Usa DefaultNamingStrategy se non specificata."""
        from rendering.rendering_engine import RenderingEngine
        from rendering.naming_strategy import DefaultNamingStrategy

        renderer = make_mock_renderer()
        engine = RenderingEngine(renderer)

        assert isinstance(engine.naming, DefaultNamingStrategy)

    def test_accepts_custom_naming_strategy(self):
        """Accetta naming strategy custom."""
        from rendering.rendering_engine import RenderingEngine

        renderer = make_mock_renderer()
        custom_naming = MagicMock()

        engine = RenderingEngine(renderer, naming_strategy=custom_naming)

        assert engine.naming is custom_naming

    def test_render_delegates_to_mode(self):
        """render() delega l'esecuzione al RenderMode."""
        from rendering.rendering_engine import RenderingEngine

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
        from rendering.rendering_engine import RenderingEngine

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
        from rendering.rendering_engine import RenderingEngine
        from rendering.render_mode import StemsRenderMode
        from rendering.naming_strategy import NamingStrategy

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
        from rendering.rendering_engine import RenderingEngine
        from rendering.render_mode import RenderMode
        from rendering.naming_strategy import DefaultNamingStrategy

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
