# tests/rendering/test_csound_renderer.py
"""
TDD suite per CsoundRenderer e RendererFactory.

CsoundRenderer: Adapter che wrappa ScoreWriter + subprocess csound
nell'interfaccia AudioRenderer ABC.

RendererFactory: Factory Method che crea il renderer giusto da stringa CLI.

Coverage:
1. TestCsoundRendererInit          - costruzione e ereditarieta' ABC
2. TestCsoundRendererRenderStream  - delega a ScoreWriter + subprocess
3. TestCsoundRendererRenderCartridge - delega per cartridges
4. TestCsoundRendererErrors        - gestione errori subprocess
5. TestRendererFactoryCreate       - creazione renderer da stringa
6. TestRendererFactoryValidation   - validazione input
"""

import pytest
from unittest.mock import MagicMock, patch, call

from rendering.audio_renderer import AudioRenderer
from rendering.csound_renderer import CsoundRenderer
from rendering.renderer_factory import RendererFactory


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_score_writer():
    """Mock ScoreWriter."""
    sw = MagicMock()
    sw.ftable_manager = MagicMock()
    return sw


@pytest.fixture
def csound_config():
    """Configurazione Csound minimale."""
    return {
        'orc_path': 'csound/main.orc',
        'env_vars': {
            'INCDIR': '/project/src',
            'SSDIR': '/project/refs',
            'SFDIR': '/project/output',
        },
        'log_dir': '/project/logs',
        'message_level': 134,
    }


@pytest.fixture
def renderer(mock_score_writer, csound_config):
    """CsoundRenderer configurato con mock."""
    return CsoundRenderer(
        score_writer=mock_score_writer,
        csound_config=csound_config,
    )


@pytest.fixture
def mock_stream():
    """Mock Stream minimale."""
    stream = MagicMock()
    stream.stream_id = 'test_stream'
    stream.voices = [[]]
    stream.grains = []
    return stream


@pytest.fixture
def mock_cartridge():
    """Mock Cartridge minimale."""
    cartridge = MagicMock()
    cartridge.cartridge_id = 'test_cartridge'
    return cartridge


# =============================================================================
# 1. TEST CSOUND RENDERER INIT
# =============================================================================

class TestCsoundRendererInit:
    """Test per la costruzione e l'ereditarieta' ABC."""

    def test_creates_instance(self, renderer):
        """CsoundRenderer si puo' istanziare."""
        assert renderer is not None

    def test_inherits_from_audio_renderer(self, renderer):
        """CsoundRenderer e' sottoclasse di AudioRenderer."""
        assert isinstance(renderer, AudioRenderer)

    def test_stores_score_writer(self, renderer, mock_score_writer):
        """score_writer viene conservato."""
        assert renderer.score_writer is mock_score_writer

    def test_stores_csound_config(self, renderer, csound_config):
        """csound_config viene conservato."""
        assert renderer.csound_config is csound_config


# =============================================================================
# 2. TEST RENDER STREAM
# =============================================================================

class TestCsoundRendererRenderStream:
    """Test per render_stream: ScoreWriter + subprocess csound."""

    @patch('rendering.csound_renderer.subprocess.run')
    def test_calls_score_writer(self, mock_run, renderer, mock_stream):
        """render_stream delega la scrittura .sco a ScoreWriter."""
        mock_run.return_value = MagicMock(returncode=0)

        renderer.render_stream(mock_stream, '/output/test.aif')

        renderer.score_writer.write_score.assert_called_once()

    @patch('rendering.csound_renderer.subprocess.run')
    def test_score_writer_receives_stream(self, mock_run, renderer, mock_stream):
        """ScoreWriter riceve lo stream nella lista."""
        mock_run.return_value = MagicMock(returncode=0)

        renderer.render_stream(mock_stream, '/output/test.aif')

        call_kwargs = renderer.score_writer.write_score.call_args.kwargs
        assert mock_stream in call_kwargs['streams']

    @patch('rendering.csound_renderer.subprocess.run')
    def test_calls_subprocess_csound(self, mock_run, renderer, mock_stream):
        """render_stream invoca csound via subprocess."""
        mock_run.return_value = MagicMock(returncode=0)

        renderer.render_stream(mock_stream, '/output/test.aif')

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == 'csound'

    @patch('rendering.csound_renderer.subprocess.run')
    def test_csound_receives_orc_path(self, mock_run, renderer, mock_stream):
        """Il comando csound include il path dell'orchestra."""
        mock_run.return_value = MagicMock(returncode=0)

        renderer.render_stream(mock_stream, '/output/test.aif')

        cmd = mock_run.call_args[0][0]
        assert 'csound/main.orc' in cmd

    @patch('rendering.csound_renderer.subprocess.run')
    def test_csound_receives_output_flag(self, mock_run, renderer, mock_stream):
        """Il comando csound include -o con il path output."""
        mock_run.return_value = MagicMock(returncode=0)

        renderer.render_stream(mock_stream, '/output/test.aif')

        cmd = mock_run.call_args[0][0]
        assert '-o' in cmd
        o_idx = cmd.index('-o')
        assert cmd[o_idx + 1] == '/output/test.aif'

    @patch('rendering.csound_renderer.subprocess.run')
    def test_returns_output_path(self, mock_run, renderer, mock_stream):
        """render_stream ritorna il path del file prodotto."""
        mock_run.return_value = MagicMock(returncode=0)

        result = renderer.render_stream(mock_stream, '/output/test.aif')

        assert result == '/output/test.aif'


# =============================================================================
# 3. TEST RENDER CARTRIDGE
# =============================================================================

class TestCsoundRendererRenderCartridge:
    """Test per render_cartridge."""

    @patch('rendering.csound_renderer.subprocess.run')
    def test_calls_score_writer_with_cartridge(self, mock_run, renderer, mock_cartridge):
        """render_cartridge delega la scrittura a ScoreWriter."""
        mock_run.return_value = MagicMock(returncode=0)

        renderer.render_cartridge(mock_cartridge, '/output/cart.aif')

        call_kwargs = renderer.score_writer.write_score.call_args.kwargs
        assert mock_cartridge in call_kwargs['cartridges']

    @patch('rendering.csound_renderer.subprocess.run')
    def test_returns_output_path(self, mock_run, renderer, mock_cartridge):
        """render_cartridge ritorna il path del file prodotto."""
        mock_run.return_value = MagicMock(returncode=0)

        result = renderer.render_cartridge(mock_cartridge, '/output/cart.aif')

        assert result == '/output/cart.aif'


# =============================================================================
# 4. TEST ERRORS
# =============================================================================

class TestCsoundRendererErrors:
    """Test per gestione errori."""

    @patch('rendering.csound_renderer.subprocess.run')
    def test_csound_failure_raises(self, mock_run, renderer, mock_stream):
        """Csound con returncode != 0 solleva RuntimeError."""
        mock_run.return_value = MagicMock(returncode=1, stderr='error')

        with pytest.raises(RuntimeError, match="Csound"):
            renderer.render_stream(mock_stream, '/output/test.aif')

    @patch('rendering.csound_renderer.subprocess.run')
    def test_csound_not_found_raises(self, mock_run, renderer, mock_stream):
        """Csound non installato solleva FileNotFoundError."""
        mock_run.side_effect = FileNotFoundError("csound not found")

        with pytest.raises(FileNotFoundError):
            renderer.render_stream(mock_stream, '/output/test.aif')


# =============================================================================
# 5. TEST RENDERER FACTORY CREATE
# =============================================================================

class TestRendererFactoryCreate:
    """Test per RendererFactory.create()."""

    def test_create_numpy_returns_numpy_renderer(self):
        """create('numpy', ...) ritorna NumpyAudioRenderer."""
        from rendering.numpy_audio_renderer import NumpyAudioRenderer
        from rendering.sample_registry import SampleRegistry
        from rendering.numpy_window_registry import NumpyWindowRegistry

        renderer = RendererFactory.create(
            renderer_type='numpy',
            sample_registry=SampleRegistry.__new__(SampleRegistry),
            window_registry=NumpyWindowRegistry(),
            table_map={},
            output_sr=48000,
        )
        assert isinstance(renderer, NumpyAudioRenderer)

    def test_create_csound_returns_csound_renderer(self):
        """create('csound', ...) ritorna CsoundRenderer."""
        renderer = RendererFactory.create(
            renderer_type='csound',
            score_writer=MagicMock(),
            csound_config={'orc_path': 'main.orc'},
        )
        assert isinstance(renderer, CsoundRenderer)

    def test_create_returns_audio_renderer_subclass(self):
        """Qualunque renderer creato e' sottoclasse di AudioRenderer."""
        r_numpy = RendererFactory.create(
            renderer_type='numpy',
            sample_registry=MagicMock(),
            window_registry=MagicMock(),
            table_map={},
            output_sr=48000,
        )
        r_csound = RendererFactory.create(
            renderer_type='csound',
            score_writer=MagicMock(),
            csound_config={},
        )
        assert isinstance(r_numpy, AudioRenderer)
        assert isinstance(r_csound, AudioRenderer)


# =============================================================================
# 6. TEST RENDERER FACTORY VALIDATION
# =============================================================================

class TestRendererFactoryValidation:
    """Test per validazione input della factory."""

    def test_invalid_type_raises_value_error(self):
        """Tipo non valido solleva ValueError."""
        with pytest.raises(ValueError, match="non supportato"):
            RendererFactory.create(renderer_type='invalid')

    def test_error_message_lists_valid_types(self):
        """Il messaggio di errore elenca i tipi validi."""
        with pytest.raises(ValueError, match="csound.*numpy"):
            RendererFactory.create(renderer_type='unknown')

    def test_case_sensitive(self):
        """Il tipo e' case-sensitive."""
        with pytest.raises(ValueError):
            RendererFactory.create(renderer_type='Numpy')

    def test_empty_string_raises(self):
        """Stringa vuota solleva ValueError."""
        with pytest.raises(ValueError):
            RendererFactory.create(renderer_type='')