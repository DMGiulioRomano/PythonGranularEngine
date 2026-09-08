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

import yaml
import yaml.reader
import pytest
from unittest.mock import MagicMock, patch


def make_mock_generator_module():
    mod = types.ModuleType('generator')
    mock_cls = MagicMock()
    mock_instance = MagicMock()
    mock_cls.return_value = mock_instance

    # Come il Generator reale: il costruttore registra yaml_path
    # sull'istanza (api.collect_cache_orphans ne deriva l'aif_prefix).
    def _ctor(yaml_path, *args, **kwargs):
        mock_instance.yaml_path = yaml_path
        return mock_instance

    mock_cls.side_effect = _ctor
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


def _make_mock_yaml_module():
    """Stub di `yaml` (e del suo `yaml.reader`) che porta pero' le classi
    d'errore, quelle vere.

    Dalla #257 `pge.shared.exceptions.ConfigParseError` eredita da
    `yaml.YAMLError` e `ConfigMarkedParseError` da `yaml.MarkedYAMLError`, e
    una classe base serve nel momento in cui la classe si crea -- non quando
    la si usa. Uno stub nudo qui non farebbe fallire un assert: manderebbe
    l'import di `pge.shared.exceptions` nel suo ramo di ripiego, quello
    scritto per il checkout senza PyYAML, dove `ConfigParseError` non e' piu'
    un `yaml.YAMLError` vero -- cioe' la promessa di libreria della #257
    cadrebbe dentro i test che dovrebbero difenderla.

    **Il modulo li chiede in due `from ... import` dentro lo stesso `try`, e
    un `from` che non trova un nome alza `ImportError`**: e' tutto il gruppo a
    mancare quando ne manca uno -- compreso il sottomodulo, che `from
    yaml.reader import ...` risolve via `sys.modules['yaml.reader']` e non
    leggendo un attributo dello stub. Perche' lo stub non resti indietro sul prossimo nome,
    `test_lo_stub_yaml_dei_test_non_manda_exceptions_nel_ripiego`
    (`tests/shared/test_engine_exceptions.py`) misura quell'import in un
    interprete figlio, con questo stub installato: e' l'unico posto dove si
    vede, perche' nel processo dei test `pge.shared.exceptions` e' gia'
    importato col `yaml` vero molto prima che questa fixture entri in scena.

    Le classi sono quelle vere di proposito: cosi' `isinstance` e
    `pytest.raises(yaml.YAMLError)` dicono la stessa cosa dentro e fuori dai
    mock. Lo stub resta uno stub per tutto il resto (parser, dumper).
    """
    mod = types.ModuleType('yaml')
    mod.YAMLError = yaml.YAMLError
    mod.MarkedYAMLError = yaml.MarkedYAMLError
    # `ReaderError` sta in `yaml.reader`, non nel namespace `yaml`: e' un
    # sottomodulo, e `from yaml.reader import ...` non guarda `mod.reader` --
    # passa da `sys.modules['yaml.reader']`. Ecco perche' questa funzione ne
    # restituisce due, ed entrambi vanno in `sys.modules`.
    sub = types.ModuleType('yaml.reader')
    sub.ReaderError = yaml.reader.ReaderError
    mod.reader = sub
    return mod, sub


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
    rendering_engine_mod = types.ModuleType('pge.rendering.rendering_engine')
    rendering_engine_mod.RenderingEngine = engine_cls

    stems_mode_cls = MagicMock(name='StemsRenderMode')
    mix_mode_cls = MagicMock(name='MixRenderMode')
    render_mode_mod = types.ModuleType('pge.rendering.render_mode')
    render_mode_mod.StemsRenderMode = stems_mode_cls
    render_mode_mod.MixRenderMode = mix_mode_cls

    factory_cls = MagicMock(name='RendererFactory')
    factory_cls.create.return_value = renderer_instance
    # available_types() finisce nei messaggi d'errore e in api.renderer_types():
    # il mock deve rispondere con l'elenco vero, altrimenti il test verifica
    # una lista inventata qui.
    from pge.rendering.renderer_factory import RendererFactory as _RealFactory
    factory_cls.available_types.return_value = _RealFactory.available_types()
    factory_mod = types.ModuleType('pge.rendering.renderer_factory')
    factory_mod.RendererFactory = factory_cls

    sample_reg_mod = types.ModuleType('pge.rendering.sample_registry')
    sample_reg_mod.SampleRegistry = MagicMock(name='SampleRegistry')

    window_reg_mod = types.ModuleType('pge.rendering.numpy_window_registry')
    window_reg_mod.NumpyWindowRegistry = MagicMock(name='NumpyWindowRegistry')

    _yaml_mock, _yaml_reader_mock = _make_mock_yaml_module()
    mock_modules = {
        'pge.engine.generator': gen_mod,
        'pge.rendering.score_visualizer': viz_mod,
        'pge.shared.logger': log_mod,
        'pge.rendering.rendering_engine': rendering_engine_mod,
        'pge.rendering.render_mode': render_mode_mod,
        'pge.rendering.renderer_factory': factory_mod,
        'pge.rendering.sample_registry': sample_reg_mod,
        'pge.rendering.numpy_window_registry': window_reg_mod,
        # dipendenze transitive
        'yaml': _yaml_mock,
        'yaml.reader': _yaml_reader_mock,
        'soundfile': types.ModuleType('soundfile'),
    }

    refs = {
        'Generator': gen_cls,
        'generator_instance': gen_inst,
        'ScoreVisualizer': viz_cls,
        'visualizer_instance': viz_inst,
        'configure_clip_logger': log_mod.configure_clip_logger,
        'configure_engine_logger': log_mod.configure_engine_logger,
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
        for mod_name in ('pge.cli', 'pge.api', 'main'):
            sys.modules.pop(mod_name, None)

        import importlib
        main_mod = importlib.import_module('pge.cli')

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


class LazyStreamDouble:
    """Stream finto con la laziness vera (#117): `.voices` esplode se lo
    stream non e' materializzato.

    Estratto da test_api.py/test_main.py, dove ne esistevano due copie
    identiche, per la ragione per cui esiste questo modulo: la fixture dei
    confini sta in un posto solo. Serve ai test di `collect_grain_counts`
    (#250) e a chiunque debba distinguere uno stream materializzato da uno
    saltato dalla cache -- un accesso di troppo e' un test rosso, non una
    lentezza silenziosa in produzione.

    `materialize()` e' il pezzo che permette di misurare il MOMENTO della
    lettura e non solo il suo esito: uno stream che nasce non materializzato
    e viene materializzato dal render finto distingue un conteggio fatto
    dopo `engine.render` da uno fatto prima.
    """

    def __init__(self, stream_id, voices=None):
        self.stream_id = stream_id
        self.generated = voices is not None
        self._voices = voices

    def materialize(self, voices):
        """Come fa il renderer: legge i grani e da quel momento `generated`
        e' True."""
        self._voices = voices
        self.generated = True

    @property
    def voices(self):
        if not self.generated:
            raise AssertionError(
                f"accesso a .voices su {self.stream_id}: innescherebbe "
                "la generazione lazy (#117)")
        return self._voices


def fake_grains(n):
    """n grani finti: `collect_grain_counts` ne guarda solo il numero."""
    return [MagicMock(name=f'grain{i}') for i in range(n)]
