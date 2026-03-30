# tests/rendering/test_audio_renderer.py
"""
TDD suite per AudioRenderer ABC.

Coverage:
1. TestAudioRendererABC              - interfaccia ABC pura
2. TestConcreteRendererContract      - sottoclassi concrete devono implementare tutti i metodi
3. TestRenderSingleStreamContract    - contratto render_single_stream()
4. TestRenderMergedStreamsContract   - contratto render_merged_streams()
"""

import pytest
from abc import ABC
from unittest.mock import MagicMock

from rendering.audio_renderer import AudioRenderer


# =============================================================================
# HELPERS: STUB CONCRETO PER TESTARE IL CONTRATTO
# =============================================================================

class StubRenderer(AudioRenderer):
    """
    Implementazione minimale per testare il contratto ABC.
    Ritorna il path ricevuto senza fare nulla.
    """

    def render_single_stream(self, stream, output_path: str) -> str:
        return output_path

    def render_merged_streams(self, streams, output_path: str) -> str:
        return output_path


class IncompleteRenderer(AudioRenderer):
    """
    Sottoclasse che implementa solo render_single_stream.
    Deve fallire all'istanziazione.
    """

    def render_single_stream(self, stream, output_path: str) -> str:
        return output_path


# =============================================================================
# 1. TEST AUDIORENDERER ABC
# =============================================================================

class TestAudioRendererABC:
    """Test per l'interfaccia AudioRenderer (Abstract Base Class)."""

    def test_inherits_from_abc(self):
        """AudioRenderer eredita da ABC."""
        assert ABC in AudioRenderer.__bases__

    def test_cannot_instantiate_directly(self):
        """Non si puo' istanziare AudioRenderer direttamente."""
        with pytest.raises(TypeError):
            AudioRenderer()

    def test_has_abstract_render_single_stream(self):
        """render_single_stream e' tra i metodi astratti."""
        assert 'render_single_stream' in AudioRenderer.__abstractmethods__

    def test_has_abstract_render_merged_streams(self):
        """render_merged_streams e' tra i metodi astratti."""
        assert 'render_merged_streams' in AudioRenderer.__abstractmethods__

    def test_exactly_two_abstract_methods(self):
        """AudioRenderer ha esattamente 2 metodi astratti."""
        assert len(AudioRenderer.__abstractmethods__) == 2


# =============================================================================
# 2. TEST CONCRETE RENDERER CONTRACT
# =============================================================================

class TestConcreteRendererContract:
    """Una sottoclasse concreta deve implementare tutti i metodi astratti."""

    def test_complete_subclass_is_instantiable(self):
        """StubRenderer (tutti i metodi) si puo' istanziare."""
        renderer = StubRenderer()
        assert isinstance(renderer, AudioRenderer)

    def test_incomplete_subclass_raises_type_error(self):
        """IncompleteRenderer (manca render_merged_streams) non si puo' istanziare."""
        with pytest.raises(TypeError):
            IncompleteRenderer()

    def test_stub_is_subclass_of_audio_renderer(self):
        """StubRenderer e' sottoclasse di AudioRenderer."""
        assert issubclass(StubRenderer, AudioRenderer)


# =============================================================================
# 3. TEST RENDER_SINGLE_STREAM CONTRACT
# =============================================================================

class TestRenderSingleStreamContract:
    """Contratto di render_single_stream(): accetta stream + output_path, ritorna str."""

    @pytest.fixture
    def renderer(self):
        return StubRenderer()

    @pytest.fixture
    def mock_stream(self):
        stream = MagicMock()
        stream.stream_id = 'test_stream'
        stream.voices = [[]]
        stream.grains = []
        return stream

    def test_returns_string(self, renderer, mock_stream):
        """render_single_stream ritorna una stringa."""
        result = renderer.render_single_stream(mock_stream, '/output/test.aif')
        assert isinstance(result, str)

    def test_returns_output_path(self, renderer, mock_stream):
        """Lo stub ritorna il path ricevuto."""
        path = '/output/test.aif'
        result = renderer.render_single_stream(mock_stream, path)
        assert result == path

    def test_accepts_stream_and_path(self, renderer, mock_stream):
        """render_single_stream accetta due argomenti posizionali senza errori."""
        renderer.render_single_stream(mock_stream, 'out.aif')


# =============================================================================
# 4. TEST RENDER_MERGED_STREAMS CONTRACT
# =============================================================================

class TestRenderMergedStreamsContract:
    """Contratto di render_merged_streams(): accetta lista stream + output_path, ritorna str."""

    @pytest.fixture
    def renderer(self):
        return StubRenderer()

    @pytest.fixture
    def mock_streams(self):
        streams = []
        for i in range(2):
            s = MagicMock()
            s.stream_id = f'stream_{i}'
            s.onset = float(i)
            s.duration = 5.0
            streams.append(s)
        return streams

    def test_returns_string(self, renderer, mock_streams):
        """render_merged_streams ritorna una stringa."""
        result = renderer.render_merged_streams(mock_streams, '/output/mix.aif')
        assert isinstance(result, str)

    def test_returns_output_path(self, renderer, mock_streams):
        """Lo stub ritorna il path ricevuto."""
        path = '/output/mix.aif'
        result = renderer.render_merged_streams(mock_streams, path)
        assert result == path

    def test_accepts_streams_and_path(self, renderer, mock_streams):
        """render_merged_streams accetta due argomenti posizionali senza errori."""
        renderer.render_merged_streams(mock_streams, 'out.aif')