# tests/test_api.py
"""
Test unit per src/api.py — l'API programmatica estratta da main.py
(Fase 1 del refactor library/CLI).

Contratto del modulo api (piano, sez. B.1):
- nessun print NEL PROPRIO MODULO, nessun sys.exit, nessuna lettura di
  sys.argv;
- errori -> eccezioni (EngineError e sottoclassi, ValueError);
- lazy import dei moduli pesanti dentro le funzioni.

Stessa tecnica di mock ai confini di test_main.py (fixture condivisa in
tests/main_mocks.py), ma senza argv e senza SystemExit: le asserzioni sono
sui kwargs esatti verso RendererFactory/RenderingEngine/engine.render, sui
campi di RenderResult, su capsys vuoto e sulle eccezioni propagate.

Cosa misurano davvero i `test_no_print` di questo file (issue #189): qui
Generator, RenderingEngine e ScoreVisualizer sono MagicMock, quindi un
capsys vuoto dice che *api.py* non stampa di suo -- ed e' vero, ed e' la
meta' del contratto che vale la pena blindare qui. Non dice niente su cosa
vede chi chiama l'API con i componenti veri: quelli stampano, e per anni la
dichiarazione in api.py ha promesso il contrario proprio perche' i mock non
potevano contraddirla. L'altra meta' sta in tests/test_api_stdout.py, che
lavora su output vero e senza mock in mezzo.
"""

import sys
import types
import pytest
from unittest.mock import MagicMock, patch

from tests.main_mocks import (
    build_mock_modules, LazyStreamDouble, fake_grains,
)


@pytest.fixture
def api_mocks():
    """Importa api in ambiente controllato (mock a sys.modules)."""
    mock_modules, refs = build_mock_modules()

    with patch.dict(sys.modules, mock_modules):
        sys.modules.pop('pge.api', None)

        import importlib
        api_mod = importlib.import_module('pge.api')

        yield {'api': api_mod, **refs}


def _make_scm_module():
    """Modulo mock per rendering.stream_cache_manager."""
    scm_cls = MagicMock(name='StreamCacheManager')
    scm_instance = MagicMock(name='scm_instance')
    scm_cls.return_value = scm_instance
    mod = types.ModuleType('pge.rendering.stream_cache_manager')
    mod.StreamCacheManager = scm_cls
    return mod, scm_cls, scm_instance


# =============================================================================
# build_renderer
# =============================================================================

class TestBuildRendererNumpy:
    """build_renderer('numpy', ...): kwargs esatti a RendererFactory.create
    (specchio delle asserzioni di TestRendererFlag in test_main.py)."""

    def _table_map(self):
        return {1: ('sample', 'voice.wav'), 2: ('window', 'hanning')}

    def test_factory_receives_numpy_type(self, api_mocks):
        gen = api_mocks['generator_instance']
        gen.ftable_manager.get_all_tables.return_value = self._table_map()
        api_mocks['api'].build_renderer('numpy', gen)
        assert api_mocks['RendererFactory'].create.call_args.args[0] == 'numpy'

    def test_factory_receives_exact_kwargs(self, api_mocks):
        gen = api_mocks['generator_instance']
        table_map = self._table_map()
        gen.ftable_manager.get_all_tables.return_value = table_map
        sdm = {'s1': {'stream_id': 's1'}}
        gen.stream_data_map = sdm

        renderer = api_mocks['api'].build_renderer('numpy', gen)

        kwargs = api_mocks['RendererFactory'].create.call_args.kwargs
        assert kwargs['table_map'] == table_map
        assert kwargs['output_sr'] == 48000          # DEFAULT_OUTPUT_SR
        assert kwargs['cache_manager'] is None       # default: cache off
        assert kwargs['stream_data_map'] is sdm
        assert kwargs['audio_format'].extension == '.aif'
        assert kwargs['jobs'] == 1                   # default API (non 'auto')
        assert renderer is api_mocks['renderer_instance']

    def test_loads_only_sample_entries(self, api_mocks):
        gen = api_mocks['generator_instance']
        gen.ftable_manager.get_all_tables.return_value = {
            1: ('sample', 'voice.wav'),
            2: ('sample', 'piano.wav'),
            3: ('window', 'hanning'),
        }
        api_mocks['api'].build_renderer('numpy', gen)

        sample_reg_cls = sys.modules['pge.rendering.sample_registry'].SampleRegistry
        sample_reg = sample_reg_cls.return_value
        loaded = [c.args[0] for c in sample_reg.load.call_args_list]
        assert sorted(loaded) == ['piano.wav', 'voice.wav']

    def test_jobs_and_output_sr_forwarded(self, api_mocks):
        gen = api_mocks['generator_instance']
        gen.ftable_manager.get_all_tables.return_value = {}
        api_mocks['api'].build_renderer('numpy', gen, jobs=4, output_sr=44100)
        kwargs = api_mocks['RendererFactory'].create.call_args.kwargs
        assert kwargs['jobs'] == 4
        assert kwargs['output_sr'] == 44100

    def test_no_print(self, api_mocks, capsys):
        gen = api_mocks['generator_instance']
        gen.ftable_manager.get_all_tables.return_value = self._table_map()
        api_mocks['api'].build_renderer('numpy', gen)
        assert capsys.readouterr().out == ''


class TestBuildRendererCsound:
    """build_renderer('csound', ..., csound=CsoundOptions(...)): csound_config
    esatto (specchio di TestCsoundArgs in test_main.py)."""

    def test_default_csound_config(self, api_mocks):
        gen = api_mocks['generator_instance']
        api_mocks['api'].build_renderer('csound', gen)

        call = api_mocks['RendererFactory'].create.call_args
        assert call.args[0] == 'csound'
        cfg = call.kwargs['csound_config']
        assert cfg == {
            'orc_path': 'csound/main.orc',
            'env_vars': {'INCDIR': 'src', 'SSDIR': 'refs', 'SFDIR': 'output'},
            'log_dir': 'logs',
            'message_level': 134,
        }
        assert call.kwargs['score_writer'] is gen.score_writer
        assert call.kwargs['sco_dir'] is None
        assert call.kwargs['cache_manager'] is None

    def test_custom_csound_options(self, api_mocks):
        api = api_mocks['api']
        gen = api_mocks['generator_instance']
        opts = api.CsoundOptions(
            orc_path='custom/orch.orc', incdir='/custom/src',
            ssdir='/audio/refs', sfdir='/audio/output',
            log_dir='/custom/logs', message_level=7, sco_dir='/tmp/sco',
        )
        api.build_renderer('csound', gen, csound=opts)

        kwargs = api_mocks['RendererFactory'].create.call_args.kwargs
        assert kwargs['csound_config'] == {
            'orc_path': 'custom/orch.orc',
            'env_vars': {'INCDIR': '/custom/src', 'SSDIR': '/audio/refs',
                         'SFDIR': '/audio/output'},
            'log_dir': '/custom/logs',
            'message_level': 7,
        }
        assert kwargs['sco_dir'] == '/tmp/sco'

    def test_no_print(self, api_mocks, capsys):
        api_mocks['api'].build_renderer(
            'csound', api_mocks['generator_instance'])
        assert capsys.readouterr().out == ''


class TestBuildRendererSuperCollider:
    """build_renderer('supercollider', ..., supercollider=SuperColliderOptions(...)):
    kwargs esatti a RendererFactory.create (issue #228)."""

    def _table_map(self):
        return {1: ('sample', 'voice.wav'), 2: ('window', 'hanning')}

    def test_factory_receives_supercollider_type(self, api_mocks):
        gen = api_mocks['generator_instance']
        gen.ftable_manager.get_all_tables.return_value = self._table_map()
        api_mocks['api'].build_renderer('supercollider', gen)
        assert api_mocks['RendererFactory'].create.call_args.args[0] == 'supercollider'

    def test_table_map_dal_generator(self, api_mocks):
        """Come il ramo numpy: i numeri di tabella del FtableManager
        diventano numeri di buffer."""
        gen = api_mocks['generator_instance']
        gen.ftable_manager.get_all_tables.return_value = self._table_map()
        api_mocks['api'].build_renderer('supercollider', gen)
        kwargs = api_mocks['RendererFactory'].create.call_args.kwargs
        assert kwargs['table_map'] == self._table_map()

    def test_default_sc_config(self, api_mocks):
        """Opzioni non specificate = chiavi assenti: il default e' quello del
        renderer, scritto in un posto solo (review PR #240)."""
        gen = api_mocks['generator_instance']
        api_mocks['api'].build_renderer('supercollider', gen)
        kwargs = api_mocks['RendererFactory'].create.call_args.kwargs
        assert kwargs['sc_config'] == {}
        assert kwargs['osc_dir'] is None
        assert kwargs['cache_manager'] is None

    def test_custom_sc_options(self, api_mocks):
        api = api_mocks['api']
        gen = api_mocks['generator_instance']
        opts = api.SuperColliderOptions(
            synthdef_source='/custom/grain.scd',
            synthdef_dir='/custom/defs',
            scsynth_bin='/opt/sc/scsynth',
            sclang_bin='/opt/sc/sclang',
            block_size=64,
            max_nodes=2048,
            osc_dir='/tmp/osc',
        )
        api.build_renderer('supercollider', gen, supercollider=opts)

        kwargs = api_mocks['RendererFactory'].create.call_args.kwargs
        assert kwargs['sc_config'] == {
            'synthdef_source': '/custom/grain.scd',
            'synthdef_dir': '/custom/defs',
            'scsynth_bin': '/opt/sc/scsynth',
            'sclang_bin': '/opt/sc/sclang',
            'block_size': 64,
            'max_nodes': 2048,
        }
        assert kwargs['osc_dir'] == '/tmp/osc'

    def test_samples_dir_col_separatore_finale(self, api_mocks):
        """SuperColliderScoreWriter concatena base + filename, come
        SampleRegistry: senza separatore il path finisce incollato."""
        gen = api_mocks['generator_instance']
        api_mocks['api'].build_renderer(
            'supercollider', gen, samples_dir='/media/wavs')
        kwargs = api_mocks['RendererFactory'].create.call_args.kwargs
        assert kwargs['samples_dir'] == '/media/wavs/'

    def test_output_sr_e_formato_inoltrati(self, api_mocks):
        from pge.rendering.audio_format import FORMATS

        gen = api_mocks['generator_instance']
        api_mocks['api'].build_renderer(
            'supercollider', gen, output_sr=96000,
            audio_format=FORMATS['wav'])
        kwargs = api_mocks['RendererFactory'].create.call_args.kwargs
        assert kwargs['output_sr'] == 96000
        assert kwargs['audio_format'] is FORMATS['wav']

    def test_cache_manager_iniettato(self, api_mocks, capsys):
        scm_mod, scm_cls, scm_instance = _make_scm_module()
        gen = api_mocks['generator_instance']

        with patch.dict(sys.modules,
                        {'pge.rendering.stream_cache_manager': scm_mod}):
            api_mocks['api'].build_renderer(
                'supercollider', gen, cache_manifest_path='cache/z.json')

        kwargs = api_mocks['RendererFactory'].create.call_args.kwargs
        assert kwargs['cache_manager'] is scm_instance
        assert kwargs['stream_data_map'] is gen.stream_data_map
        assert capsys.readouterr().out == ''

    def test_nessun_sample_caricato_in_memoria(self, api_mocks):
        """A differenza del ramo numpy: i sample li legge scsynth, non noi.
        Caricarli qui sarebbe il doppio della RAM per niente."""
        gen = api_mocks['generator_instance']
        gen.ftable_manager.get_all_tables.return_value = self._table_map()
        sample_reg = sys.modules['pge.rendering.sample_registry'].SampleRegistry
        api_mocks['api'].build_renderer('supercollider', gen)
        sample_reg.assert_not_called()

    def test_no_print(self, api_mocks, capsys):
        api_mocks['api'].build_renderer(
            'supercollider', api_mocks['generator_instance'])
        assert capsys.readouterr().out == ''


class TestRendererTypes:
    """api.renderer_types(): l'elenco dei backend, per chi deve mostrarlo
    (CLI, PGE-ui) senza tenerne una copia propria."""

    def test_include_i_tre_backend(self, api_mocks):
        tipi = api_mocks['api'].renderer_types()
        assert 'numpy' in tipi
        assert 'csound' in tipi
        assert 'supercollider' in tipi

    def test_errore_su_tipo_ignoto_li_elenca_tutti(self, api_mocks):
        from pge.shared.exceptions import InvalidRendererError
        with pytest.raises(InvalidRendererError) as exc:
            api_mocks['api'].build_renderer(
                'bogus', api_mocks['generator_instance'])
        assert 'supercollider' in exc.value.available


class TestBuildRendererCache:
    """cache_manifest_path esplicito -> StreamCacheManager(cache_path=...)
    iniettato nel factory, senza print (il print [CACHE] e' policy CLI)."""

    def test_manifest_path_injected_numpy(self, api_mocks, capsys):
        scm_mod, scm_cls, scm_instance = _make_scm_module()
        gen = api_mocks['generator_instance']
        gen.ftable_manager.get_all_tables.return_value = {}

        with patch.dict(sys.modules,
                        {'pge.rendering.stream_cache_manager': scm_mod}):
            api_mocks['api'].build_renderer(
                'numpy', gen, cache_manifest_path='cache/x.json')

        scm_cls.assert_called_once_with(cache_path='cache/x.json',
                                        samples_dir=None,
                                        renderer_type='numpy')
        kwargs = api_mocks['RendererFactory'].create.call_args.kwargs
        assert kwargs['cache_manager'] is scm_instance
        assert capsys.readouterr().out == ''

    def test_manifest_path_injected_csound(self, api_mocks, capsys):
        scm_mod, scm_cls, scm_instance = _make_scm_module()
        gen = api_mocks['generator_instance']

        with patch.dict(sys.modules,
                        {'pge.rendering.stream_cache_manager': scm_mod}):
            api_mocks['api'].build_renderer(
                'csound', gen, cache_manifest_path='cache/y.json')

        scm_cls.assert_called_once_with(cache_path='cache/y.json',
                                        samples_dir=None,
                                        renderer_type='csound')
        kwargs = api_mocks['RendererFactory'].create.call_args.kwargs
        assert kwargs['cache_manager'] is scm_instance
        assert capsys.readouterr().out == ''


    def test_samples_dir_reaches_the_cache_manager(self, api_mocks):
        """Il fingerprint di uno stream senza `duration` (#205) risolve la
        durata dal file audio: senza samples_dir cercherebbe in PATHSAMPLES
        anche quando i sample stanno altrove, e la risoluzione fallirebbe in
        silenzio."""
        scm_mod, scm_cls, _ = _make_scm_module()
        gen = api_mocks['generator_instance']

        with patch.dict(sys.modules,
                        {'pge.rendering.stream_cache_manager': scm_mod}):
            api_mocks['api'].build_renderer(
                'csound', gen, cache_manifest_path='cache/y.json',
                samples_dir='/media/wavs')

        scm_cls.assert_called_once_with(cache_path='cache/y.json',
                                        samples_dir='/media/wavs',
                                        renderer_type='csound')


class TestBuildRendererUnknownType:
    """Tipo ignoto -> InvalidRendererError (e NON SystemExit)."""

    def test_raises_invalid_renderer_error(self, api_mocks):
        from pge.shared.exceptions import InvalidRendererError
        with pytest.raises(InvalidRendererError):
            api_mocks['api'].build_renderer(
                'bogus', api_mocks['generator_instance'])

    def test_does_not_raise_system_exit(self, api_mocks):
        try:
            api_mocks['api'].build_renderer(
                'bogus', api_mocks['generator_instance'])
        except SystemExit:  # pragma: no cover
            pytest.fail("build_renderer non deve chiamare sys.exit")
        except Exception:
            pass


# =============================================================================
# collect_cache_orphans
# =============================================================================

class TestCollectCacheOrphans:
    """GC del manifest cache (estrazione del blocco GC di main):
    tutti gli stream_id del YAML, aif_dir dall'output, prefix dal
    basename dello yaml del generator; no-op senza cache_manager."""

    def _gen_with_yaml(self, api_mocks, yaml_stream_ids):
        gen = api_mocks['generator_instance']
        gen.yaml_path = 'configs/PGE_test.yml'
        gen.data = {
            'streams': [{'stream_id': sid} for sid in yaml_stream_ids]
        }
        return gen

    def _renderer_with_cache(self):
        renderer = MagicMock(name='renderer')
        renderer.cache_manager = MagicMock(name='cache_manager')
        renderer.cache_manager.garbage_collect.return_value = []
        return renderer

    def test_noop_without_cache_manager(self, api_mocks):
        gen = self._gen_with_yaml(api_mocks, ['s1'])
        renderer = MagicMock(name='renderer')
        renderer.cache_manager = None

        removed = api_mocks['api'].collect_cache_orphans(
            gen, renderer, 'out.aif')

        assert removed == []

    def test_uses_all_yaml_stream_ids(self, api_mocks):
        """Solo/mute filtra generator.streams, ma il GC deve usare TUTTI
        gli stream del YAML (generator.data)."""
        gen = self._gen_with_yaml(api_mocks, ['s1', 's2', 's3'])
        gen.streams = [MagicMock()]        # filtrato (solo attivo)
        renderer = self._renderer_with_cache()

        api_mocks['api'].collect_cache_orphans(gen, renderer, 'out.aif')

        kwargs = renderer.cache_manager.garbage_collect.call_args.kwargs
        assert set(kwargs['current_stream_ids']) == {'s1', 's2', 's3'}

    def test_aif_dir_from_output_path(self, api_mocks):
        import os
        gen = self._gen_with_yaml(api_mocks, ['s1'])
        renderer = self._renderer_with_cache()

        api_mocks['api'].collect_cache_orphans(
            gen, renderer, '/custom/output/mix.aif')

        kwargs = renderer.cache_manager.garbage_collect.call_args.kwargs
        assert kwargs['aif_dir'] == os.path.abspath('/custom/output')

    def test_prefix_from_generator_yaml_basename(self, api_mocks):
        gen = self._gen_with_yaml(api_mocks, ['s1'])
        renderer = self._renderer_with_cache()

        api_mocks['api'].collect_cache_orphans(gen, renderer, 'out.aif')

        kwargs = renderer.cache_manager.garbage_collect.call_args.kwargs
        assert kwargs['aif_prefix'] == 'PGE_test'

    def test_ext_from_audio_format(self, api_mocks):
        from pge.rendering.audio_format import FORMATS
        gen = self._gen_with_yaml(api_mocks, ['s1'])
        renderer = self._renderer_with_cache()

        api_mocks['api'].collect_cache_orphans(
            gen, renderer, 'out.wav', audio_format=FORMATS['wav'])

        kwargs = renderer.cache_manager.garbage_collect.call_args.kwargs
        assert kwargs['ext'] == '.wav'

    def test_returns_removed_list(self, api_mocks):
        gen = self._gen_with_yaml(api_mocks, ['s1'])
        renderer = self._renderer_with_cache()
        renderer.cache_manager.garbage_collect.return_value = ['orfano1']

        removed = api_mocks['api'].collect_cache_orphans(
            gen, renderer, 'out.aif')

        assert removed == ['orfano1']

    def test_no_print(self, api_mocks, capsys):
        gen = self._gen_with_yaml(api_mocks, ['s1'])
        renderer = self._renderer_with_cache()
        renderer.cache_manager.garbage_collect.return_value = ['orfano1']

        api_mocks['api'].collect_cache_orphans(gen, renderer, 'out.aif')

        assert capsys.readouterr().out == ''


# =============================================================================
# render
# =============================================================================

class TestRender:
    """render(): RenderingEngine + DefaultNamingStrategy + Mix/Stems,
    campi di RenderResult, run_cache_gc, renderer istanza o stringa."""

    def _gen(self, api_mocks, streams=None):
        gen = api_mocks['generator_instance']
        gen.streams = streams if streams is not None else []
        gen.ftable_manager.get_all_tables.return_value = {}
        return gen

    def test_engine_built_with_renderer_and_naming_strategy(self, api_mocks):
        gen = self._gen(api_mocks)
        api_mocks['api'].render(gen, 'out.aif', renderer='numpy')

        call = api_mocks['RenderingEngine'].call_args
        assert call.args[0] is api_mocks['renderer_instance']
        naming = call.kwargs['naming_strategy']
        assert naming.ext == '.aif'   # DefaultNamingStrategy reale

    def test_naming_strategy_ext_follows_format(self, api_mocks):
        from pge.rendering.audio_format import FORMATS
        gen = self._gen(api_mocks)
        api_mocks['api'].render(
            gen, 'out.wav', renderer='numpy', audio_format=FORMATS['wav'])

        naming = api_mocks['RenderingEngine'].call_args.kwargs['naming_strategy']
        assert naming.ext == '.wav'

    def test_mix_mode_by_default(self, api_mocks):
        gen = self._gen(api_mocks)
        api_mocks['api'].render(gen, 'out.aif', renderer='numpy')

        api_mocks['MixRenderMode'].assert_called_once()
        api_mocks['StemsRenderMode'].assert_not_called()
        mode = api_mocks['engine_instance'].render.call_args.kwargs['mode']
        assert mode is api_mocks['MixRenderMode'].return_value

    def test_stems_mode_with_per_stream(self, api_mocks):
        gen = self._gen(api_mocks)
        api_mocks['api'].render(
            gen, 'out.aif', renderer='numpy', per_stream=True)

        api_mocks['StemsRenderMode'].assert_called_once()
        api_mocks['MixRenderMode'].assert_not_called()

    def test_engine_render_receives_streams_and_output_path(self, api_mocks):
        s1, s2 = MagicMock(), MagicMock()
        gen = self._gen(api_mocks, streams=[s1, s2])
        api_mocks['api'].render(gen, 'canzone.aif', renderer='numpy')

        kwargs = api_mocks['engine_instance'].render.call_args.kwargs
        assert kwargs['streams'] == [s1, s2]
        assert kwargs['output_path'] == 'canzone.aif'

    def test_render_result_fields(self, api_mocks):
        gen = self._gen(api_mocks)
        api_mocks['engine_instance'].render.return_value = ['/out/a.aif']
        api_mocks['renderer_instance'].jobs = 3

        result = api_mocks['api'].render(gen, 'out.aif', renderer='numpy')

        assert result.audio_paths == ['/out/a.aif']
        assert result.renderer_type == 'numpy'
        assert result.per_stream is False
        assert result.jobs == 3
        assert result.elapsed_seconds >= 0.0
        assert result.gc_removed == []

    def test_renderer_string_forwards_build_kwargs(self, api_mocks):
        gen = self._gen(api_mocks)
        api_mocks['api'].render(
            gen, 'out.aif', renderer='numpy', jobs=2, output_sr=44100)

        kwargs = api_mocks['RendererFactory'].create.call_args.kwargs
        assert kwargs['jobs'] == 2
        assert kwargs['output_sr'] == 44100

    def test_renderer_instance_used_as_is(self, api_mocks):
        """renderer=istanza (escape hatch CLI): factory NON richiamato."""
        gen = self._gen(api_mocks)
        my_renderer = MagicMock(name='my_renderer')

        api_mocks['api'].render(gen, 'out.aif', renderer=my_renderer)

        api_mocks['RendererFactory'].create.assert_not_called()
        assert api_mocks['RenderingEngine'].call_args.args[0] is my_renderer

    def test_renderer_instance_type_from_declared_attribute(self, api_mocks):
        """renderer=istanza: RenderResult.renderer_type e' l'attributo
        `renderer_type` dichiarato dal renderer, non un'euristica sul nome
        della classe."""
        gen = self._gen(api_mocks)

        class WrappedRenderer:            # nome senza 'csound' nel nome
            renderer_type = 'csound'
            cache_manager = None

        result = api_mocks['api'].render(
            gen, 'out.aif', renderer=WrappedRenderer())

        assert result.renderer_type == 'csound'

    def test_renderer_instance_without_declared_type_is_unknown(self, api_mocks):
        """Renderer custom che non dichiara renderer_type: 'unknown',
        niente etichette inventate."""
        gen = self._gen(api_mocks)

        class BareRenderer:
            cache_manager = None

        result = api_mocks['api'].render(
            gen, 'out.aif', renderer=BareRenderer())

        assert result.renderer_type == 'unknown'

    def test_run_cache_gc_default_in_stems(self, api_mocks):
        """per_stream + cache manager presente: GC eseguito prima del render
        e orfani riportati in gc_removed."""
        gen = self._gen(api_mocks)
        gen.yaml_path = 'configs/PGE_test.yml'
        gen.data = {'streams': [{'stream_id': 's1'}]}
        my_renderer = MagicMock(name='my_renderer')
        my_renderer.cache_manager.garbage_collect.return_value = ['orfano']

        result = api_mocks['api'].render(
            gen, 'out.aif', renderer=my_renderer, per_stream=True)

        my_renderer.cache_manager.garbage_collect.assert_called_once()
        assert result.gc_removed == ['orfano']

    def test_run_cache_gc_false_skips_gc(self, api_mocks):
        gen = self._gen(api_mocks)
        my_renderer = MagicMock(name='my_renderer')

        result = api_mocks['api'].render(
            gen, 'out.aif', renderer=my_renderer, per_stream=True,
            run_cache_gc=False)

        my_renderer.cache_manager.garbage_collect.assert_not_called()
        assert result.gc_removed == []

    def test_no_gc_in_mix_mode(self, api_mocks):
        """MIX mode: niente GC (solo STEMS ha build incrementale)."""
        gen = self._gen(api_mocks)
        my_renderer = MagicMock(name='my_renderer')

        api_mocks['api'].render(gen, 'out.aif', renderer=my_renderer)

        my_renderer.cache_manager.garbage_collect.assert_not_called()

    def test_no_print(self, api_mocks, capsys):
        gen = self._gen(api_mocks)
        api_mocks['api'].render(gen, 'out.aif', renderer='numpy')
        assert capsys.readouterr().out == ''


# =============================================================================
# collect_grain_counts / RenderResult.grain_counts
# =============================================================================

class TestCollectGrainCounts:
    """collect_grain_counts: lettura PASSIVA a valle del render (issue #250).

    Il conteggio esce da `voices` -- unica fonte di verita' (#201) -- e solo
    sugli stream gia' materializzati: leggere `.voices` su uno stream con
    `generated` falso innescherebbe la generazione lazy (#117), cioe'
    rigenererebbe in fase di stampa proprio i grani che la cache ha appena
    fatto risparmiare.
    """

    _Stream = LazyStreamDouble

    def _grains(self, n):
        return fake_grains(n)

    def test_stream_materializzato_conta_grani_e_voci(self, api_mocks):
        gen = api_mocks['generator_instance']
        gen.streams = [self._Stream(
            's1', [self._grains(10), self._grains(7), self._grains(3)])]

        counts = api_mocks['api'].collect_grain_counts(gen)

        assert counts['s1'].grains == 20
        assert counts['s1'].voices == 3

    def test_stream_non_materializzato_vale_none(self, api_mocks):
        """Cache-clean: nessun numero inventato, e nessuna lettura di
        .voices (la _Stream finta solleverebbe)."""
        gen = api_mocks['generator_instance']
        gen.streams = [self._Stream('s_clean')]

        counts = api_mocks['api'].collect_grain_counts(gen)

        assert counts == {'s_clean': None}

    def test_ogni_stream_ha_una_voce_nella_mappa(self, api_mocks):
        """Anche i cache-clean compaiono: la CLI stampa da questa mappa e non
        deve tornare a iterare generator.streams per sapere chi manca."""
        gen = api_mocks['generator_instance']
        gen.streams = [
            self._Stream('s1', [self._grains(2)]),
            self._Stream('s2'),
            self._Stream('s3', [self._grains(1), self._grains(1)]),
        ]

        counts = api_mocks['api'].collect_grain_counts(gen)

        assert list(counts) == ['s1', 's2', 's3']   # ordine di generator.streams
        assert counts['s1'].grains == 2
        assert counts['s2'] is None
        assert counts['s3'].voices == 2

    def test_stream_senza_attributo_generated_vale_none(self, api_mocks):
        """Stream duck-typed di un consumer esterno: si assume non
        materializzato (direzione sicura, nessun accesso a .voices)."""
        class Foreign:
            stream_id = 'esterno'

            @property
            def voices(self):
                raise AssertionError('non deve essere letto')

        gen = api_mocks['generator_instance']
        gen.streams = [Foreign()]

        assert api_mocks['api'].collect_grain_counts(gen) == {'esterno': None}

    def test_render_popola_grain_counts(self, api_mocks):
        gen = api_mocks['generator_instance']
        gen.ftable_manager.get_all_tables.return_value = {}
        gen.streams = [
            self._Stream('s1', [self._grains(4), self._grains(4)]),
            self._Stream('s2'),
        ]

        result = api_mocks['api'].render(gen, 'out.aif', renderer='numpy')

        assert result.grain_counts['s1'].grains == 8
        assert result.grain_counts['s1'].voices == 2
        assert result.grain_counts['s2'] is None

    def test_render_conta_dopo_engine_render_non_prima(self, api_mocks):
        """Il MOMENTO della lettura e' il vincolo di #250, non un dettaglio.

        Qui gli stream nascono non materializzati ed e' `engine.render` a
        materializzarne uno: se `collect_grain_counts` risalisse sopra la
        chiamata al render, la mappa direbbe `None` per tutti -- e in
        produzione quel `None` sarebbe il caso buono, perche' sugli stream
        veri leggere `.voices` prima del render li genererebbe in fase di
        stampa, che e' esattamente il lavoro che #117 aveva tolto. Gli altri
        test della classe usano stream gia' materializzati alla costruzione,
        quindi non distinguono il prima dal dopo.
        """
        gen = api_mocks['generator_instance']
        gen.ftable_manager.get_all_tables.return_value = {}
        dirty = self._Stream('s_dirty')
        clean = self._Stream('s_clean')   # saltato dalla cache: nessuno lo tocca
        gen.streams = [dirty, clean]

        def _render_materializza(*args, **kwargs):
            dirty.materialize([self._grains(3), self._grains(2)])
            return ['/out/test.aif']

        api_mocks['engine_instance'].render.side_effect = _render_materializza

        result = api_mocks['api'].render(gen, 'out.aif', renderer='numpy')

        assert result.grain_counts['s_dirty'].grains == 5
        assert result.grain_counts['s_dirty'].voices == 2
        assert result.grain_counts['s_clean'] is None

    def test_render_result_default_e_mappa_vuota(self, api_mocks):
        """Chi costruisce un RenderResult a mano (CLI test, consumer) non
        deve passare il campo."""
        result = api_mocks['api'].RenderResult(
            audio_paths=[], elapsed_seconds=0.0,
            renderer_type='numpy', per_stream=False)
        assert result.grain_counts == {}


# =============================================================================
# load_generator / render_file
# =============================================================================

class TestLoadGenerator:
    """load_generator: Generator(yaml) + load_yaml() + create_elements(),
    errori propagati come eccezioni, nessun print proprio."""

    def test_three_step_flow(self, api_mocks):
        gen = api_mocks['api'].load_generator('test.yml')

        api_mocks['Generator'].assert_called_once_with('test.yml')
        inst = api_mocks['generator_instance']
        inst.load_yaml.assert_called_once()
        inst.create_elements.assert_called_once()
        assert gen is inst

    def test_propagates_engine_error(self, api_mocks):
        from pge.shared.exceptions import SampleNotFoundError
        err = SampleNotFoundError(filename='x.wav', search_path='./refs/')
        api_mocks['generator_instance'].load_yaml.side_effect = err

        with pytest.raises(SampleNotFoundError):
            api_mocks['api'].load_generator('test.yml')

    def test_propagates_file_not_found(self, api_mocks):
        api_mocks['generator_instance'].load_yaml.side_effect = (
            FileNotFoundError('missing'))

        with pytest.raises(FileNotFoundError):
            api_mocks['api'].load_generator('missing.yml')

    def test_config_file_not_found_resta_catturabile_come_builtin(
            self, api_mocks):
        """La docstring promette `FileNotFoundError` fra i `Raises` (#257).

        `load_yaml` solleva ora `ConfigFileNotFoundError`, che eredita il
        builtin proprio perche' questa promessa non si rompa per chi usa
        `pge.api` come libreria.
        """
        from pge.shared.exceptions import ConfigFileNotFoundError

        api_mocks['generator_instance'].load_yaml.side_effect = (
            ConfigFileNotFoundError('missing.yml'))

        with pytest.raises(FileNotFoundError):
            api_mocks['api'].load_generator('missing.yml')

    def test_config_parse_error_resta_catturabile_come_yaml_error(
            self, api_mocks):
        """Specchio del precedente per lo YAML malformato (#257)."""
        import yaml
        from pge.shared.exceptions import ConfigParseError

        api_mocks['generator_instance'].load_yaml.side_effect = (
            ConfigParseError('broken.yml', yaml.YAMLError('boom')))

        with pytest.raises(yaml.YAMLError):
            api_mocks['api'].load_generator('broken.yml')

    def test_config_read_error_resta_catturabile_come_os_error(
            self, api_mocks):
        """La terza delle tre promesse di libreria (#257).

        La docstring di `load_generator` dichiara `OSError` accanto agli altri
        due builtin, e le altre due promesse hanno gia' il loro caso qui: senza
        questo, la piu' recente delle tre e' l'unica che nessuno misura dal
        lato chiamante.
        """
        from pge.shared.exceptions import ConfigReadError

        api_mocks['generator_instance'].load_yaml.side_effect = ConfigReadError(
            'configs/', IsADirectoryError(21, 'Is a directory', 'configs/'))

        with pytest.raises(OSError):
            api_mocks['api'].load_generator('configs/')

    def test_no_own_print(self, api_mocks, capsys):
        api_mocks['api'].load_generator('test.yml')
        assert capsys.readouterr().out == ''


class TestRenderFile:
    """render_file: composizione load_generator + render; audio_format
    come stringa -> lookup FORMATS, stringa ignota -> ValueError."""

    def test_composes_load_and_render(self, api_mocks):
        api_mocks['engine_instance'].render.return_value = ['/out/f.aif']

        result = api_mocks['api'].render_file(
            'test.yml', 'out.aif', renderer='numpy')

        api_mocks['Generator'].assert_called_once_with('test.yml')
        api_mocks['generator_instance'].load_yaml.assert_called_once()
        kwargs = api_mocks['engine_instance'].render.call_args.kwargs
        assert kwargs['output_path'] == 'out.aif'
        assert result.audio_paths == ['/out/f.aif']

    def test_audio_format_string_lookup(self, api_mocks):
        api_mocks['api'].render_file(
            'test.yml', 'out.wav', renderer='numpy', audio_format='wav')

        kwargs = api_mocks['RendererFactory'].create.call_args.kwargs
        assert kwargs['audio_format'].extension == '.wav'

    def test_unknown_format_string_raises_value_error(self, api_mocks):
        with pytest.raises(ValueError) as exc_info:
            api_mocks['api'].render_file(
                'test.yml', 'out.mp3', renderer='numpy', audio_format='mp3')
        # il messaggio elenca i formati validi
        for label in ('aif', 'aiff', 'wav', 'flac'):
            assert label in str(exc_info.value)

    def test_unknown_format_does_not_touch_generator(self, api_mocks):
        """La validazione del formato avviene prima di caricare lo yaml."""
        with pytest.raises(ValueError):
            api_mocks['api'].render_file(
                'test.yml', 'out.mp3', audio_format='mp3')
        api_mocks['Generator'].assert_not_called()

    def test_run_cache_gc_false_skips_gc(self, api_mocks):
        """run_cache_gc=False esposto anche nella one-shot API: un chiamante
        STEMS+cache puo' evitare la cancellazione degli stem orfani senza
        dover scendere a load_generator + render."""
        gen = api_mocks['generator_instance']
        gen.data = {'streams': [{'stream_id': 's1'}]}

        api_mocks['api'].render_file(
            'test.yml', 'out.aif', renderer='numpy', per_stream=True,
            run_cache_gc=False)

        renderer = api_mocks['renderer_instance']
        renderer.cache_manager.garbage_collect.assert_not_called()


# =============================================================================
# export_*
# =============================================================================

class TestExportReaper:
    """export_reaper: replica del blocco --reaper incluso il padding MIX."""

    def _writer_mock(self):
        writer_instance = MagicMock(name='reaper_writer_instance')
        writer_cls = MagicMock(name='ReaperProjectWriter',
                               return_value=writer_instance)
        mod = types.ModuleType('pge.export.reaper_project_writer')
        mod.ReaperProjectWriter = writer_cls
        return mod, writer_instance

    def test_stems_paths_passed_as_is(self, api_mocks):
        mod, writer = self._writer_mock()
        gen = api_mocks['generator_instance']
        gen.streams = [MagicMock(), MagicMock()]
        paths = ['/out/s1.aif', '/out/s2.aif']

        with patch.dict(sys.modules, {'pge.export.reaper_project_writer': mod}):
            out = api_mocks['api'].export_reaper(gen, paths, 'proj.rpp')

        kwargs = writer.write.call_args.kwargs
        assert kwargs['streams'] == gen.streams
        assert kwargs['aif_paths'] == paths
        assert kwargs['output_path'] == 'proj.rpp'
        assert out == 'proj.rpp'

    def test_mix_padding_replicates_single_path(self, api_mocks):
        """In MIX mode (1 file, N stream) ogni TRACK punta al mix."""
        mod, writer = self._writer_mock()
        gen = api_mocks['generator_instance']
        gen.streams = [MagicMock(), MagicMock(), MagicMock()]

        with patch.dict(sys.modules, {'pge.export.reaper_project_writer': mod}):
            api_mocks['api'].export_reaper(gen, ['/out/mix.aif'], 'p.rpp')

        kwargs = writer.write.call_args.kwargs
        assert kwargs['aif_paths'] == ['/out/mix.aif'] * 3

    def test_no_print(self, api_mocks, capsys):
        mod, _ = self._writer_mock()
        gen = api_mocks['generator_instance']
        gen.streams = [MagicMock()]
        with patch.dict(sys.modules, {'pge.export.reaper_project_writer': mod}):
            api_mocks['api'].export_reaper(gen, ['/out/mix.aif'], 'p.rpp')
        assert capsys.readouterr().out == ''


class TestExportSv:
    """export_sv: SVExporter().export(streams, audio, out, layout).
    La policy 'ignora in STEMS' resta nella CLI."""

    def _sv_mock(self):
        mod = types.ModuleType('pge.export.sv_exporter')
        cls = MagicMock(name='SVExporter')
        mod.SVExporter = cls
        return mod, cls

    def test_export_called_with_kwargs(self, api_mocks):
        mod, cls = self._sv_mock()
        gen = api_mocks['generator_instance']
        gen.streams = [MagicMock()]

        with patch.dict(sys.modules, {'pge.export.sv_exporter': mod}):
            out = api_mocks['api'].export_sv(
                gen, '/out/mix.aif', 'sess.sv', layout='single')

        call = cls.return_value.export.call_args
        assert call.args[0] == gen.streams
        assert call.kwargs['audio_path'] == '/out/mix.aif'
        assert call.kwargs['out_path'] == 'sess.sv'
        assert call.kwargs['layout'] == 'single'
        assert out == 'sess.sv'

    def test_default_layout_multi(self, api_mocks):
        mod, cls = self._sv_mock()
        gen = api_mocks['generator_instance']

        with patch.dict(sys.modules, {'pge.export.sv_exporter': mod}):
            api_mocks['api'].export_sv(gen, 'a.aif', 's.sv')

        assert cls.return_value.export.call_args.kwargs['layout'] == 'multi'


class TestExportGrainJson:
    """export_grain_json: scrive il sidecar solo per stream con
    .generated True (generazione lazy, issue #117)."""

    def _writer_mock(self):
        writer_instance = MagicMock(name='grain_json_writer')
        writer_instance.write.side_effect = (
            lambda stream, d, b: f"{d}/{b}__{stream.stream_id}__grains.json")
        cls = MagicMock(return_value=writer_instance)
        mod = types.ModuleType('pge.export.grain_json_writer')
        mod.GrainJsonWriter = cls
        return mod, writer_instance

    def _stream(self, stream_id, generated):
        s = MagicMock()
        s.stream_id = stream_id
        s.generated = generated
        return s

    def test_writes_only_generated_streams(self, api_mocks):
        mod, writer = self._writer_mock()
        gen = api_mocks['generator_instance']
        s_gen = self._stream('s1', True)
        s_clean = self._stream('s2', False)
        gen.streams = [s_gen, s_clean]

        with patch.dict(sys.modules, {'pge.export.grain_json_writer': mod}):
            paths = api_mocks['api'].export_grain_json(gen, '/out', 'base')

        written = [c.args[0] for c in writer.write.call_args_list]
        assert written == [s_gen]
        assert paths == ['/out/base__s1__grains.json']

    def test_writes_all_when_all_generated(self, api_mocks):
        mod, writer = self._writer_mock()
        gen = api_mocks['generator_instance']
        gen.streams = [self._stream('s1', True), self._stream('s2', True)]

        with patch.dict(sys.modules, {'pge.export.grain_json_writer': mod}):
            paths = api_mocks['api'].export_grain_json(gen, '/out', 'base')

        assert len(paths) == 2


class TestExportScorePdf:
    """export_score_pdf: config default identica alla CLI, merge dei
    parametri passati, ritorna pdf_path."""

    CLI_DEFAULT_CONFIG = {
        'page_duration': 15.0,
        'show_static_params': False,
        'show_voice_offsets': False,
        'envelope_filter': None,
        'magnify_auto': False,
        'magnify_targets': [],
        'grain_height': 'duration',
        'bw': False,
    }

    def test_defaults_never_shadow_the_bw_preset(self, api_mocks):
        """I default dell'API stanno SOPRA il preset `bw`, che e' un default a
        sua volta: `from_overrides` non puo' distinguere un default dell'API
        da una scelta dell'utente. Il giorno in cui questo dict acquistasse una
        chiave che il preset sposta, `--bw` diventerebbe inerte in silenzio.
        Le due chiavi devono restare disgiunte (issue #248)."""
        from pge.rendering.visualizer_config import VisualizerConfig

        collisione = (set(self.CLI_DEFAULT_CONFIG)
                      & set(VisualizerConfig._bw_defaults()))
        assert not collisione, sorted(collisione)

    def test_default_config_matches_cli(self, api_mocks):
        gen = api_mocks['generator_instance']
        out = api_mocks['api'].export_score_pdf(gen, 'score.pdf')

        viz_cls = api_mocks['ScoreVisualizer']
        call = viz_cls.call_args
        assert call.args[0] is gen
        assert call.kwargs['config'] == self.CLI_DEFAULT_CONFIG
        viz_cls.return_value.export_pdf.assert_called_once_with('score.pdf')
        assert out == 'score.pdf'

    def test_config_merge_overrides_defaults(self, api_mocks):
        gen = api_mocks['generator_instance']
        api_mocks['api'].export_score_pdf(
            gen, 'score.pdf', config={'page_duration': 30.0})

        cfg = api_mocks['ScoreVisualizer'].call_args.kwargs['config']
        assert cfg['page_duration'] == 30.0
        assert cfg['show_static_params'] is False   # default preservato

    def test_no_print(self, api_mocks, capsys):
        api_mocks['api'].export_score_pdf(
            api_mocks['generator_instance'], 'score.pdf')
        assert capsys.readouterr().out == ''


# =============================================================================
# samples_dir (Fase 2 refactor library/CLI)
# =============================================================================

class TestSamplesDirFlow:
    """samples_dir fluisce da api a Generator / SampleRegistry / SSDIR /
    export_score_pdf; assente -> parita' col comportamento storico."""

    def test_load_generator_forwards_samples_dir(self, api_mocks):
        api_mocks['api'].load_generator('test.yml', samples_dir='/campioni/')
        api_mocks['Generator'].assert_called_once_with(
            'test.yml', samples_dir='/campioni/')

    def test_load_generator_without_samples_dir_keeps_legacy_call(self, api_mocks):
        """Senza samples_dir la chiamata resta Generator(yaml): compatibile
        con firme Generator precedenti (submodule non aggiornati)."""
        api_mocks['api'].load_generator('test.yml')
        api_mocks['Generator'].assert_called_once_with('test.yml')

    def test_build_renderer_numpy_injects_sample_registry_base_path(self, api_mocks):
        gen = api_mocks['generator_instance']
        gen.ftable_manager.get_all_tables.return_value = {}

        api_mocks['api'].build_renderer('numpy', gen, samples_dir='/campioni/')

        sample_reg_cls = sys.modules['pge.rendering.sample_registry'].SampleRegistry
        sample_reg_cls.assert_called_once_with(base_path='/campioni/')

    def test_build_renderer_numpy_without_samples_dir_keeps_default(self, api_mocks):
        gen = api_mocks['generator_instance']
        gen.ftable_manager.get_all_tables.return_value = {}

        api_mocks['api'].build_renderer('numpy', gen)

        sample_reg_cls = sys.modules['pge.rendering.sample_registry'].SampleRegistry
        sample_reg_cls.assert_called_once_with()

    def test_csound_ssdir_from_samples_dir_normalized(self, api_mocks):
        """CsoundOptions.ssdir None -> samples_dir senza slash finale."""
        gen = api_mocks['generator_instance']

        api_mocks['api'].build_renderer('csound', gen, samples_dir='/campioni/')

        kwargs = api_mocks['RendererFactory'].create.call_args.kwargs
        assert kwargs['csound_config']['env_vars']['SSDIR'] == '/campioni'

    def test_csound_explicit_ssdir_wins_over_samples_dir(self, api_mocks):
        api = api_mocks['api']
        gen = api_mocks['generator_instance']

        api.build_renderer('csound', gen, samples_dir='/campioni/',
                           csound=api.CsoundOptions(ssdir='/altro/refs'))

        kwargs = api_mocks['RendererFactory'].create.call_args.kwargs
        assert kwargs['csound_config']['env_vars']['SSDIR'] == '/altro/refs'

    def test_csound_no_samples_dir_falls_back_to_refs(self, api_mocks):
        gen = api_mocks['generator_instance']
        api_mocks['api'].build_renderer('csound', gen)
        kwargs = api_mocks['RendererFactory'].create.call_args.kwargs
        assert kwargs['csound_config']['env_vars']['SSDIR'] == 'refs'

    def test_render_forwards_samples_dir_to_build(self, api_mocks):
        gen = api_mocks['generator_instance']
        gen.streams = []
        gen.ftable_manager.get_all_tables.return_value = {}

        api_mocks['api'].render(gen, 'out.aif', renderer='numpy',
                                samples_dir='/campioni/')

        sample_reg_cls = sys.modules['pge.rendering.sample_registry'].SampleRegistry
        sample_reg_cls.assert_called_once_with(base_path='/campioni/')

    def test_render_file_forwards_samples_dir(self, api_mocks):
        gen = api_mocks['generator_instance']
        gen.streams = []
        gen.ftable_manager.get_all_tables.return_value = {}

        api_mocks['api'].render_file('test.yml', 'out.aif', renderer='numpy',
                                     samples_dir='/campioni/')

        api_mocks['Generator'].assert_called_once_with(
            'test.yml', samples_dir='/campioni/')
        sample_reg_cls = sys.modules['pge.rendering.sample_registry'].SampleRegistry
        sample_reg_cls.assert_called_once_with(base_path='/campioni/')

    def test_export_score_pdf_injects_samples_dir_in_config(self, api_mocks):
        gen = api_mocks['generator_instance']

        api_mocks['api'].export_score_pdf(gen, 'score.pdf',
                                          samples_dir='/campioni/')

        cfg = api_mocks['ScoreVisualizer'].call_args.kwargs['config']
        assert cfg['samples_dir'] == '/campioni/'
        assert cfg['page_duration'] == 15.0   # default preservato

    def test_export_score_pdf_without_samples_dir_keeps_cli_config(self, api_mocks):
        """Senza samples_dir la config resta quella storica della CLI
        (nessuna chiave samples_dir iniettata: il default None vive nel
        default_config del visualizer)."""
        gen = api_mocks['generator_instance']

        api_mocks['api'].export_score_pdf(gen, 'score.pdf')

        cfg = api_mocks['ScoreVisualizer'].call_args.kwargs['config']
        assert 'samples_dir' not in cfg


class TestSamplesDirNormalization:
    """L'API garantisce il separatore finale dove serve la concatenazione
    base + filename (SampleRegistry, config del visualizer), come faceva
    engine_bridge di granulation-studies."""

    def test_sample_registry_base_path_gets_trailing_sep(self, api_mocks):
        gen = api_mocks['generator_instance']
        gen.ftable_manager.get_all_tables.return_value = {}

        api_mocks['api'].build_renderer('numpy', gen, samples_dir='/campioni')

        sample_reg_cls = sys.modules['pge.rendering.sample_registry'].SampleRegistry
        sample_reg_cls.assert_called_once_with(base_path='/campioni/')

    def test_export_score_pdf_config_gets_trailing_sep(self, api_mocks):
        gen = api_mocks['generator_instance']

        api_mocks['api'].export_score_pdf(gen, 'f.pdf', samples_dir='/campioni')

        cfg = api_mocks['ScoreVisualizer'].call_args.kwargs['config']
        assert cfg['samples_dir'] == '/campioni/'

    def test_ssdir_still_without_trailing_sep(self, api_mocks):
        """Convenzione csound: SSDIR senza slash finale anche se samples_dir
        arriva gia' normalizzato."""
        gen = api_mocks['generator_instance']
        api_mocks['api'].build_renderer('csound', gen, samples_dir='/campioni')
        kwargs = api_mocks['RendererFactory'].create.call_args.kwargs
        assert kwargs['csound_config']['env_vars']['SSDIR'] == '/campioni'


# =============================================================================
# parameter_bounds (issue #163)
# =============================================================================

class TestParameterBoundsApi:
    """parameter_bounds(): esposizione pubblica dei bounds del registry con
    override dinamici (grain_duration <- output_sr, loop_* <- sample_dur_sec).

    Funzione pura senza dipendenze pesanti: si importa pge.api reale,
    senza la fixture api_mocks.
    """

    def test_no_args_returns_static_registry(self):
        """Senza argomenti: tutte le chiavi del registry, bounds statici."""
        from pge import api
        from pge.parameters.parameter_definitions import GRANULAR_PARAMETERS

        result = api.parameter_bounds()

        assert set(result) == set(GRANULAR_PARAMETERS)
        for name, bounds in result.items():
            assert bounds == GRANULAR_PARAMETERS[name]

    @pytest.mark.parametrize('sr', [44100, 48000, 96000])
    def test_output_sr_overrides_grain_duration_min(self, sr):
        """Con output_sr: grain_duration.min_val = 1 campione (1/output_sr),
        tutti gli altri parametri restano statici."""
        from pge import api
        from pge.parameters.parameter_definitions import GRANULAR_PARAMETERS

        result = api.parameter_bounds(output_sr=sr)

        assert result['grain_duration'].min_val == 1.0 / sr
        assert result['grain_duration'].max_val == \
            GRANULAR_PARAMETERS['grain_duration'].max_val
        for name, bounds in result.items():
            if name != 'grain_duration':
                assert bounds == GRANULAR_PARAMETERS[name]

    def test_sample_dur_sec_overrides_loop_max(self):
        """Con sample_dur_sec: max_val dei parametri loop = durata del file,
        tutti gli altri parametri restano statici."""
        from pge import api
        from pge.parameters.parameter_definitions import GRANULAR_PARAMETERS

        result = api.parameter_bounds(sample_dur_sec=7.5)

        loop_params = {'loop_dur', 'loop_start', 'loop_end'}
        for name in loop_params:
            assert result[name].max_val == 7.5
            assert result[name].min_val == GRANULAR_PARAMETERS[name].min_val
        for name, bounds in result.items():
            if name not in loop_params:
                assert bounds == GRANULAR_PARAMETERS[name]

    def test_both_overrides_together(self):
        """output_sr e sample_dur_sec insieme: entrambi gli override attivi."""
        from pge import api

        result = api.parameter_bounds(output_sr=48000, sample_dur_sec=3.2)

        assert result['grain_duration'].min_val == 1.0 / 48000
        assert result['loop_dur'].max_val == 3.2
        assert result['loop_start'].max_val == 3.2
        assert result['loop_end'].max_val == 3.2

    def test_returns_fresh_dict(self):
        """Il dict e' nuovo a ogni chiamata: mutarlo non tocca il registry."""
        from pge import api
        from pge.parameters.parameter_definitions import GRANULAR_PARAMETERS

        result = api.parameter_bounds()
        result.pop('density')
        result['fittizio'] = None

        assert 'density' in GRANULAR_PARAMETERS
        assert 'fittizio' not in GRANULAR_PARAMETERS
        assert 'density' in api.parameter_bounds()

    @pytest.mark.parametrize('kwargs', [
        {'output_sr': 0},
        {'output_sr': -44100},
        {'sample_dur_sec': 0.0},
        {'sample_dur_sec': -1.0},
    ])
    def test_non_positive_args_raise_value_error(self, kwargs):
        """Contratto api.py: argomenti API invalidi -> ValueError."""
        from pge import api

        with pytest.raises(ValueError):
            api.parameter_bounds(**kwargs)

    def test_parameter_bounds_type_is_reexported(self):
        """pge.api.ParameterBounds e' la stessa classe del modulo interno:
        i consumer tipizzano il risultato senza import interni."""
        from pge import api
        from pge.parameters.parameter_definitions import ParameterBounds

        assert api.ParameterBounds is ParameterBounds
        assert isinstance(
            api.parameter_bounds()['density'], api.ParameterBounds)
