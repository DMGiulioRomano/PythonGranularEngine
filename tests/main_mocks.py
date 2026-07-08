# tests/main_mocks.py
"""
Fixture condivisa per i test che importano `main` in ambiente controllato.

Estratta da test_main.py (Fase 1 del refactor library/CLI) per essere
riusata da test_main.py, test_cli_contract.py e test_api.py senza
duplicazione: i mock a sys.modules bloccano le dipendenze pesanti
(Generator, ScoreVisualizer, logger, subsystem rendering) e i lazy import
dentro main()/api trovano i mock a runtime.
"""

import sys
import types
import pytest
from unittest.mock import MagicMock, patch


def make_mock_generator_module():
    mod = types.ModuleType('generator')
    mock_cls = MagicMock()
    mock_instance = MagicMock()
    mock_cls.return_value = mock_instance
    mod.Generator = mock_cls
    return mod, mock_cls, mock_instance


def make_mock_score_visualizer_module():
    mod = types.ModuleType('score_visualizer')
    mock_cls = MagicMock()
    mock_instance = MagicMock()
    mock_cls.return_value = mock_instance
    mod.ScoreVisualizer = mock_cls
    # Universo finto ma realistico dei nomi validi per --plot-envelopes:
    # main.py lo importa per la validazione (issue #101)
    mod.PLOT_ENVELOPE_KEYS = frozenset(
        {'volume', 'pitch', 'density', 'volume_prob'})
    return mod, mock_cls, mock_instance


def make_mock_logger_module():
    mod = types.ModuleType('logger')
    mod.configure_clip_logger = MagicMock()
    mod.get_clip_log_path = MagicMock(return_value='/tmp/test.log')
    mod.configure_engine_logger = MagicMock()
    mod.get_engine_logger = MagicMock(return_value=MagicMock())
    mod.get_engine_log_path = MagicMock(return_value='/tmp/engine.log')
    return mod


def build_mock_modules():
    """Costruisce il dict {nome_modulo: modulo mock} e i riferimenti utili.

    Ritorna (mock_modules, refs) dove refs e' il dict che la fixture
    `mocks` espone ai test.
    """
    gen_mod, gen_cls, gen_inst = make_mock_generator_module()
    viz_mod, viz_cls, viz_inst = make_mock_score_visualizer_module()
    log_mod = make_mock_logger_module()

    # Defaults necessari per il flusso unificato OCP
    gen_inst.ftable_manager.get_all_tables.return_value = {}
    gen_inst.streams = []
    gen_inst.stream_data_map = {}
    gen_inst.score_writer = MagicMock()

    # --- Mock rendering subsystem ---
    renderer_instance = MagicMock(name='renderer_instance')

    engine_cls = MagicMock(name='RenderingEngine')
    engine_instance = MagicMock(name='engine_instance')
    engine_instance.render.return_value = ['/out/test.aif']
    engine_cls.return_value = engine_instance
    rendering_engine_mod = types.ModuleType('rendering.rendering_engine')
    rendering_engine_mod.RenderingEngine = engine_cls

    stems_mode_cls = MagicMock(name='StemsRenderMode')
    mix_mode_cls = MagicMock(name='MixRenderMode')
    render_mode_mod = types.ModuleType('rendering.render_mode')
    render_mode_mod.StemsRenderMode = stems_mode_cls
    render_mode_mod.MixRenderMode = mix_mode_cls

    factory_cls = MagicMock(name='RendererFactory')
    factory_cls.create.return_value = renderer_instance
    factory_mod = types.ModuleType('rendering.renderer_factory')
    factory_mod.RendererFactory = factory_cls

    sample_reg_mod = types.ModuleType('rendering.sample_registry')
    sample_reg_mod.SampleRegistry = MagicMock(name='SampleRegistry')

    window_reg_mod = types.ModuleType('rendering.numpy_window_registry')
    window_reg_mod.NumpyWindowRegistry = MagicMock(name='NumpyWindowRegistry')

    mock_modules = {
        'engine.generator': gen_mod,
        'rendering.score_visualizer': viz_mod,
        'shared.logger': log_mod,
        'rendering.rendering_engine': rendering_engine_mod,
        'rendering.render_mode': render_mode_mod,
        'rendering.renderer_factory': factory_mod,
        'rendering.sample_registry': sample_reg_mod,
        'rendering.numpy_window_registry': window_reg_mod,
        # dipendenze transitive
        'yaml': types.ModuleType('yaml'),
        'soundfile': types.ModuleType('soundfile'),
    }

    refs = {
        'Generator': gen_cls,
        'generator_instance': gen_inst,
        'ScoreVisualizer': viz_cls,
        'visualizer_instance': viz_inst,
        'configure_clip_logger': log_mod.configure_clip_logger,
        'get_clip_log_path': log_mod.get_clip_log_path,
        'RenderingEngine': engine_cls,
        'engine_instance': engine_instance,
        'StemsRenderMode': stems_mode_cls,
        'MixRenderMode': mix_mode_cls,
        'RendererFactory': factory_cls,
        'renderer_instance': renderer_instance,
    }
    return mock_modules, refs


@pytest.fixture
def mocks():
    """
    Restituisce un dict con tutti i mock necessari e importa main
    in un ambiente controllato.

    Usa yield per mantenere sys.modules patchato durante l'intero test:
    i lazy imports dentro main() trovano i mock corretti anche a runtime.
    """
    mock_modules, refs = build_mock_modules()

    with patch.dict(sys.modules, mock_modules):
        # Forza reimport di main (e di api, la seam estratta in Fase 1)
        # in ogni test per avere stato pulito
        if 'main' in sys.modules:
            del sys.modules['main']
        sys.modules.pop('api', None)

        import importlib
        main_mod = importlib.import_module('main')

        yield {'main': main_mod, **refs}


def run_main(mocks, argv_list):
    """Esegue main.main() con sys.argv specificato."""
    with patch.dict(sys.modules, {
        'generator': sys.modules.get('generator', MagicMock()),
        'score_visualizer': sys.modules.get('score_visualizer', MagicMock()),
        'logger': sys.modules.get('logger', MagicMock()),
    }):
        with patch.object(sys, 'argv', argv_list):
            mocks['main'].main()
