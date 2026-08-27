# tests/rendering/test_supercollider_renderer.py
"""
Suite TDD per SuperColliderRenderer e il suo ramo di RendererFactory
(issue #228).

Il renderer e' un adapter sottile, come CsoundRenderer: score -> subprocess
-> file audio. Quello che si puo' verificare senza SuperCollider installato
e' tutto cio' che sta prima e dopo il subprocess -- la riga di comando, la
compilazione della SynthDef, la cache, gli errori -- ed e' esattamente cio'
che qui si verifica. La resa sonora sta nell'e2e, che salta se scsynth non
c'e'.

Copertura:
1. TestInit                 - costruzione e contratto ABC
2. TestSynthDef             - compilazione una volta sola, errori leggibili
3. TestCommand              - la riga di comando di scsynth
4. TestRenderSingleStream   - STEMS: score relativo + subprocess
5. TestRenderMergedStreams  - MIX: score assoluto + subprocess
6. TestKeepOsc              - osc_dir: lo score resta su disco per il debug
7. TestErrors               - exit code e binari mancanti
8. TestCache                - skip degli stream clean, update dopo la build
9. TestFactory              - RendererFactory conosce 'supercollider'
"""

import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from pge.core.grain import Grain
from pge.rendering.audio_format import FORMATS
from pge.rendering.audio_renderer import AudioRenderer
from pge.rendering.numpy_window_registry import NumpyWindowRegistry
from pge.rendering.renderer_factory import RendererFactory
from pge.rendering.supercollider_renderer import SuperColliderRenderer


TABLE_MAP = {1: ('sample', 'pino.wav'), 2: ('window', 'hanning')}


class FakeStream:
    def __init__(self, stream_id='s1', onset=0.0, duration=1.0, voices=None):
        self.stream_id = stream_id
        self.onset = onset
        self.duration = duration
        self.voices = voices if voices is not None else [[]]


def grain(onset=0.0, duration=0.05):
    return Grain(onset=onset, duration=duration, pointer_pos=0.0,
                 pitch_ratio=1.0, volume=0.0, pan=45.0,
                 sample_table=1, envelope_table=2)


@pytest.fixture
def synthdef_file(tmp_path):
    """Un .scsyndef gia' compilato: il caso normale dopo il primo render."""
    path = tmp_path / "pgeGrain.scsyndef"
    path.write_bytes(b'SCgf-FAKE-DEF')
    return path


@pytest.fixture
def renderer(tmp_path, synthdef_file):
    return SuperColliderRenderer(
        table_map=TABLE_MAP,
        window_registry=NumpyWindowRegistry(),
        samples_dir=str(tmp_path),
        sc_config={'synthdef_dir': str(tmp_path)},
    )


def ok(**kwargs):
    return MagicMock(returncode=0, stdout='', stderr='', **kwargs)


# =============================================================================
# 1. INIT
# =============================================================================

class TestInit:

    def test_e_un_audio_renderer(self, renderer):
        assert isinstance(renderer, AudioRenderer)

    def test_dichiara_il_proprio_tipo(self, renderer):
        assert renderer.renderer_type == 'supercollider'
        assert SuperColliderRenderer.renderer_type == 'supercollider'

    def test_render_streams_ereditato_dalla_abc(self, renderer):
        """Nessun override: il loop sequenziale dell'ABC va bene, il
        parallelismo qui e' dentro scsynth."""
        assert (SuperColliderRenderer.render_streams
                is AudioRenderer.render_streams)


# =============================================================================
# 2. SYNTHDEF
# =============================================================================

class TestSynthDef:

    def test_usa_il_def_gia_compilato(self, renderer, synthdef_file):
        with patch('pge.rendering.supercollider_renderer.subprocess.run') as run:
            assert renderer.synthdef_bytes() == b'SCgf-FAKE-DEF'
        run.assert_not_called()

    def test_compila_se_manca(self, tmp_path):
        source = tmp_path / "pge_grain.scd"
        source.write_text("// sorgente")
        out = tmp_path / "defs"
        out.mkdir()
        renderer = SuperColliderRenderer(
            table_map=TABLE_MAP, window_registry=NumpyWindowRegistry(),
            samples_dir=str(tmp_path),
            sc_config={'synthdef_source': str(source),
                       'synthdef_dir': str(out)},
        )

        def fake_sclang(cmd, **kwargs):
            (out / "pgeGrain.scsyndef").write_bytes(b'COMPILATO')
            return ok()

        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   side_effect=fake_sclang) as run:
            assert renderer.synthdef_bytes() == b'COMPILATO'

        cmd = run.call_args.args[0]
        assert cmd[0].endswith('sclang')
        assert cmd[1] == str(source)
        assert run.call_args.kwargs['env']['PGE_SYNTHDEF_DIR'] == str(out)

    def test_ricompila_se_il_sorgente_e_piu_recente(self, tmp_path):
        """Il .scsyndef e' un artefatto di build: se il .scd cambia, il def
        vecchio e' un grafo che non e' piu' quello scritto."""
        source = tmp_path / "pge_grain.scd"
        source.write_text("// v2")
        compiled = tmp_path / "pgeGrain.scsyndef"
        compiled.write_bytes(b'VECCHIO')
        os.utime(compiled, (1, 1))          # def molto piu' vecchio del sorgente

        renderer = SuperColliderRenderer(
            table_map=TABLE_MAP, window_registry=NumpyWindowRegistry(),
            samples_dir=str(tmp_path),
            sc_config={'synthdef_source': str(source),
                       'synthdef_dir': str(tmp_path)},
        )

        def fake_sclang(cmd, **kwargs):
            compiled.write_bytes(b'NUOVO')
            return ok()

        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   side_effect=fake_sclang):
            assert renderer.synthdef_bytes() == b'NUOVO'

    def test_compila_una_volta_sola(self, tmp_path):
        source = tmp_path / "pge_grain.scd"
        source.write_text("// sorgente")

        renderer = SuperColliderRenderer(
            table_map=TABLE_MAP, window_registry=NumpyWindowRegistry(),
            samples_dir=str(tmp_path),
            sc_config={'synthdef_source': str(source),
                       'synthdef_dir': str(tmp_path)},
        )

        def fake_sclang(cmd, **kwargs):
            (tmp_path / "pgeGrain.scsyndef").write_bytes(b'X')
            return ok()

        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   side_effect=fake_sclang) as run:
            renderer.synthdef_bytes()
            renderer.synthdef_bytes()
        assert run.call_count == 1

    def test_sclang_gira_headless(self, tmp_path):
        """sclang su Debian/Ubuntu e' linkato a Qt: senza un display aborta
        con SIGABRT (`qt.qpa.xcb: could not connect to display`) prima di
        eseguire una riga dello script. Su un runner CI, o su un server, e'
        la condizione normale -- non un caso limite."""
        source = tmp_path / "pge_grain.scd"
        source.write_text("// sorgente")

        renderer = SuperColliderRenderer(
            table_map=TABLE_MAP, window_registry=NumpyWindowRegistry(),
            samples_dir=str(tmp_path),
            sc_config={'synthdef_source': str(source),
                       'synthdef_dir': str(tmp_path)},
        )

        def fake_sclang(cmd, **kwargs):
            (tmp_path / "pgeGrain.scsyndef").write_bytes(b'X')
            return ok()

        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   side_effect=fake_sclang) as run:
            renderer.synthdef_bytes()

        assert run.call_args.kwargs['env']['QT_QPA_PLATFORM'] == 'offscreen'

    def test_una_scelta_esplicita_di_piattaforma_qt_vince(self, tmp_path,
                                                          monkeypatch):
        """Chi ha un display e lo vuole usare non deve essere scavalcato: il
        default vale come default, non come imposizione."""
        monkeypatch.setenv('QT_QPA_PLATFORM', 'xcb')
        source = tmp_path / "pge_grain.scd"
        source.write_text("// sorgente")

        renderer = SuperColliderRenderer(
            table_map=TABLE_MAP, window_registry=NumpyWindowRegistry(),
            samples_dir=str(tmp_path),
            sc_config={'synthdef_source': str(source),
                       'synthdef_dir': str(tmp_path)},
        )

        def fake_sclang(cmd, **kwargs):
            (tmp_path / "pgeGrain.scsyndef").write_bytes(b'X')
            return ok()

        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   side_effect=fake_sclang) as run:
            renderer.synthdef_bytes()

        assert run.call_args.kwargs['env']['QT_QPA_PLATFORM'] == 'xcb'

    def test_sclang_assente_e_un_errore_azionabile(self, tmp_path):
        from pge.shared.exceptions import SuperColliderNotFoundError

        source = tmp_path / "pge_grain.scd"
        source.write_text("// sorgente")
        renderer = SuperColliderRenderer(
            table_map=TABLE_MAP, window_registry=NumpyWindowRegistry(),
            samples_dir=str(tmp_path),
            sc_config={'synthdef_source': str(source),
                       'synthdef_dir': str(tmp_path)},
        )

        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   side_effect=FileNotFoundError()):
            with pytest.raises(SuperColliderNotFoundError) as exc:
                renderer.synthdef_bytes()

        msg = exc.value.user_message()
        assert 'sclang' in msg
        assert 'make sc-synthdef' in msg

    def test_sorgente_assente_e_un_errore_esplicito(self, tmp_path):
        from pge.shared.exceptions import SuperColliderNotFoundError

        renderer = SuperColliderRenderer(
            table_map=TABLE_MAP, window_registry=NumpyWindowRegistry(),
            samples_dir=str(tmp_path),
            sc_config={'synthdef_source': str(tmp_path / 'assente.scd'),
                       'synthdef_dir': str(tmp_path)},
        )
        with pytest.raises(SuperColliderNotFoundError):
            renderer.synthdef_bytes()

    def test_sclang_fallito_riporta_stderr(self, tmp_path):
        from pge.shared.exceptions import SuperColliderRenderError

        source = tmp_path / "pge_grain.scd"
        source.write_text("// rotto")
        renderer = SuperColliderRenderer(
            table_map=TABLE_MAP, window_registry=NumpyWindowRegistry(),
            samples_dir=str(tmp_path),
            sc_config={'synthdef_source': str(source),
                       'synthdef_dir': str(tmp_path)},
        )
        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   return_value=MagicMock(returncode=1, stdout='',
                                          stderr='ERROR: Parse error')):
            with pytest.raises(SuperColliderRenderError) as exc:
                renderer.synthdef_bytes()
        assert 'Parse error' in exc.value.user_message()

    def test_sclang_a_zero_ma_senza_def_e_comunque_un_errore(self, tmp_path):
        """sclang esce 0 anche quando lo script non ha scritto nulla: senza
        questo controllo l'errore arriverebbe a valle, come uno score che
        spedisce una SynthDef vuota."""
        from pge.shared.exceptions import SuperColliderRenderError

        source = tmp_path / "pge_grain.scd"
        source.write_text("// non scrive nulla")
        renderer = SuperColliderRenderer(
            table_map=TABLE_MAP, window_registry=NumpyWindowRegistry(),
            samples_dir=str(tmp_path),
            sc_config={'synthdef_source': str(source),
                       'synthdef_dir': str(tmp_path)},
        )
        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   return_value=ok()):
            with pytest.raises(SuperColliderRenderError):
                renderer.synthdef_bytes()


class TestSynthDefNonEStrizzataDaClean:
    """Il .scsyndef e' un artefatto persistente e non puo' stare dove
    `make clean` passa (review PR #240, punto 1).

    Il default era `generated`, cioe' `$(GENDIR)`, che `make clean` svuota --
    e con `CACHE=false` il clean e' un prerequisito di `all`. Ogni build
    ricompilava la SynthDef con sclang, il che non e' un guasto (il fallback
    funziona) ma smentisce la premessa del design: sclang una volta per
    checkout, il rendering solo scsynth. Diventava una dipendenza di runtime,
    con l'avvio di Qt in mezzo.
    """

    def test_default_fuori_da_gendir(self):
        from pge.rendering.supercollider_renderer import DEFAULT_SYNTHDEF_DIR
        assert DEFAULT_SYNTHDEF_DIR != 'generated'

    def test_default_accanto_al_sorgente(self):
        """Sta accanto al .scd che lo genera, come un .o accanto al .c."""
        import os
        from pge.rendering.supercollider_renderer import (
            DEFAULT_SYNTHDEF_DIR, DEFAULT_SYNTHDEF_SOURCE,
        )
        assert DEFAULT_SYNTHDEF_DIR == os.path.dirname(DEFAULT_SYNTHDEF_SOURCE)

    def test_api_e_renderer_concordano(self):
        """Tre default della stessa cosa (renderer, API, CLI) che divergono
        sono tre comportamenti diversi a seconda di come si entra."""
        from pge.api import SuperColliderOptions
        from pge.rendering.supercollider_renderer import DEFAULT_SYNTHDEF_DIR
        assert SuperColliderOptions().synthdef_dir == DEFAULT_SYNTHDEF_DIR

# =============================================================================
# 3. RIGA DI COMANDO
# =============================================================================

class TestCommand:

    def _cmd(self, renderer, output='/out/x.aif'):
        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   return_value=ok()) as run:
            renderer.render_single_stream(FakeStream(), output)
        return run.call_args.args[0]

    def test_forma_generale(self, renderer):
        cmd = self._cmd(renderer)
        assert cmd[0].endswith('scsynth')
        # I 6 argomenti posizionali di -N, nell'ordine imposto da scsynth.
        i = cmd.index('-N')
        assert cmd[i + 1].endswith('.osc')
        assert cmd[i + 2] == '_'                 # nessun file di input
        assert cmd[i + 3] == '/out/x.aif'
        assert cmd[i + 4] == '48000'
        assert cmd[i + 5] == 'AIFF'
        assert cmd[i + 6] == 'float'

    def test_le_opzioni_precedono_N(self, renderer):
        """scsynth interpreta come posizionali tutto cio' che segue -N."""
        cmd = self._cmd(renderer)
        i = cmd.index('-N')
        assert '-o' in cmd[:i] and '-z' in cmd[:i]

    def test_due_canali_di_uscita_zero_di_ingresso(self, renderer):
        cmd = self._cmd(renderer)
        assert cmd[cmd.index('-o') + 1] == '2'
        assert cmd[cmd.index('-i') + 1] == '0'

    def test_block_size_uno_per_default(self, renderer):
        """Onset campione-accurati: e' la stessa scelta di main.orc, che gira
        a ksmps=1 (sr=kr=48000). Con il block size di default gli onset si
        quantizzerebbero a 1.33 ms, che nella sintesi granulare non e' un
        dettaglio."""
        cmd = self._cmd(renderer)
        assert cmd[cmd.index('-z') + 1] == '1'

    def test_max_nodes_configurabile(self, tmp_path, synthdef_file):
        """E' il limite che il commento descrive come quello che fa morire il
        render a meta': deve essere raggiungibile senza passare dall'API
        (review PR #240, punto 4)."""
        renderer = SuperColliderRenderer(
            table_map=TABLE_MAP, window_registry=NumpyWindowRegistry(),
            samples_dir=str(tmp_path),
            sc_config={'synthdef_dir': str(tmp_path), 'max_nodes': 4096},
        )
        cmd = self._cmd(renderer)
        assert cmd[cmd.index('-n') + 1] == '4096'

    def test_block_size_configurabile(self, tmp_path, synthdef_file):
        renderer = SuperColliderRenderer(
            table_map=TABLE_MAP, window_registry=NumpyWindowRegistry(),
            samples_dir=str(tmp_path),
            sc_config={'synthdef_dir': str(tmp_path), 'block_size': 64},
        )
        assert self._cmd(renderer)[self._cmd(renderer).index('-z') + 1] == '64'

    def test_formato_audio_tradotto(self, tmp_path, synthdef_file):
        for label, header, sample_format in [
            ('aiff', 'AIFF', 'float'),
            ('wav', 'WAV', 'float'),
            ('flac', 'FLAC', 'int24'),
        ]:
            renderer = SuperColliderRenderer(
                table_map=TABLE_MAP, window_registry=NumpyWindowRegistry(),
                samples_dir=str(tmp_path), audio_format=FORMATS[label],
                sc_config={'synthdef_dir': str(tmp_path)},
            )
            cmd = self._cmd(renderer, output=f'/out/x{FORMATS[label].extension}')
            i = cmd.index('-N')
            assert cmd[i + 5] == header
            assert cmd[i + 6] == sample_format

    def test_sample_rate_dal_renderer(self, tmp_path, synthdef_file):
        renderer = SuperColliderRenderer(
            table_map=TABLE_MAP, window_registry=NumpyWindowRegistry(),
            samples_dir=str(tmp_path), output_sr=96000,
            sc_config={'synthdef_dir': str(tmp_path)},
        )
        cmd = self._cmd(renderer)
        assert cmd[cmd.index('-N') + 4] == '96000'


# =============================================================================
# 4. STEMS
# =============================================================================

class TestRenderSingleStream:

    def test_ritorna_il_path(self, renderer):
        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   return_value=ok()):
            got = renderer.render_single_stream(FakeStream(), '/out/x.aif')
        assert got == '/out/x.aif'

    def test_score_scritto_e_poi_rimosso(self, renderer):
        visto = {}

        def spia(cmd, **kwargs):
            path = cmd[cmd.index('-N') + 1]
            visto['path'] = path
            visto['esisteva'] = os.path.exists(path)
            return ok()

        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   side_effect=spia):
            renderer.render_single_stream(FakeStream(), '/out/x.aif')

        assert visto['esisteva'], "lo score deve esistere quando scsynth parte"
        assert not os.path.exists(visto['path']), "temporaneo non ripulito"

    def test_onset_relativi(self, renderer):
        """STEMS: lo stream parte da zero nel proprio file."""
        from tests.rendering.test_osc import decode_nrt

        stream = FakeStream(onset=5.0, duration=1.0, voices=[[grain(5.5)]])
        catturato = {}

        def spia(cmd, **kwargs):
            path = cmd[cmd.index('-N') + 1]
            with open(path, 'rb') as f:
                catturato['bundles'] = decode_nrt(f.read())
            return ok()

        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   side_effect=spia):
            renderer.render_single_stream(stream, '/out/x.aif')

        tempi = [t for t, elements in catturato['bundles']
                 for addr, _ in elements if addr == '/s_new']
        assert tempi == [pytest.approx(0.5)]

    def test_lo_score_contiene_la_synthdef_compilata(self, renderer):
        from tests.rendering.test_osc import decode_nrt

        catturato = {}

        def spia(cmd, **kwargs):
            with open(cmd[cmd.index('-N') + 1], 'rb') as f:
                catturato['bundles'] = decode_nrt(f.read())
            return ok()

        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   side_effect=spia):
            renderer.render_single_stream(FakeStream(), '/out/x.aif')

        blob = [args[0] for _, elements in catturato['bundles']
                for addr, args in elements if addr == '/d_recv']
        assert blob == [b'SCgf-FAKE-DEF']


# =============================================================================
# 5. MIX
# =============================================================================

class TestRenderMergedStreams:

    def test_ritorna_il_path(self, renderer):
        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   return_value=ok()):
            got = renderer.render_merged_streams(
                [FakeStream(), FakeStream('s2')], '/out/mix.aif')
        assert got == '/out/mix.aif'

    def test_onset_assoluti(self, renderer):
        from tests.rendering.test_osc import decode_nrt

        s1 = FakeStream('s1', 0.0, 1.0, [[grain(0.5)]])
        s2 = FakeStream('s2', 10.0, 1.0, [[grain(10.5)]])
        catturato = {}

        def spia(cmd, **kwargs):
            with open(cmd[cmd.index('-N') + 1], 'rb') as f:
                catturato['bundles'] = decode_nrt(f.read())
            return ok()

        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   side_effect=spia):
            renderer.render_merged_streams([s1, s2], '/out/mix.aif')

        tempi = [t for t, elements in catturato['bundles']
                 for addr, _ in elements if addr == '/s_new']
        assert tempi == [pytest.approx(0.5), pytest.approx(10.5)]

    def test_la_cache_non_tocca_il_mix(self, tmp_path, synthdef_file):
        """Come in CsoundRenderer: la build incrementale e' per stem."""
        cache = MagicMock()
        renderer = SuperColliderRenderer(
            table_map=TABLE_MAP, window_registry=NumpyWindowRegistry(),
            samples_dir=str(tmp_path), cache_manager=cache,
            stream_data_map={'s1': {'stream_id': 's1'}},
            sc_config={'synthdef_dir': str(tmp_path)},
        )
        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   return_value=ok()):
            renderer.render_merged_streams([FakeStream()], '/out/mix.aif')
        cache.is_dirty.assert_not_called()


# =============================================================================
# 6. KEEP-OSC
# =============================================================================

class TestKeepOsc:

    def test_score_conservato_con_nome_deterministico(self, tmp_path, synthdef_file):
        osc_dir = tmp_path / "generated"
        renderer = SuperColliderRenderer(
            table_map=TABLE_MAP, window_registry=NumpyWindowRegistry(),
            samples_dir=str(tmp_path), osc_dir=str(osc_dir),
            sc_config={'synthdef_dir': str(tmp_path)},
        )
        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   return_value=ok()):
            renderer.render_single_stream(FakeStream(), '/out/brano__s1.aif')

        assert (osc_dir / "brano__s1.osc").exists()

    def test_directory_creata_se_manca(self, tmp_path, synthdef_file):
        osc_dir = tmp_path / "a" / "b"
        renderer = SuperColliderRenderer(
            table_map=TABLE_MAP, window_registry=NumpyWindowRegistry(),
            samples_dir=str(tmp_path), osc_dir=str(osc_dir),
            sc_config={'synthdef_dir': str(tmp_path)},
        )
        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   return_value=ok()):
            renderer.render_single_stream(FakeStream(), '/out/x.aif')
        assert osc_dir.is_dir()


# =============================================================================
# 7. ERRORI
# =============================================================================

class TestFormatoNonSupportato:
    """Un subtype che scsynth non conosce e' un errore di CONFIGURAZIONE, non
    un binario che non si trova (review PR #240, punto 3). Il ramo non e'
    raggiungibile dalla CLI -- i tre FORMATS sono tutti mappati -- ma lo e'
    da un AudioFormat costruito a mano via API, ed e' li' che il messaggio
    conta: 'SuperCollider: formato campione X non trovato' manda a cercare
    un'installazione che c'e'."""

    def test_e_un_config_error(self, tmp_path, synthdef_file):
        from pge.rendering.audio_format import AudioFormat
        from pge.shared.exceptions import ConfigError, SuperColliderNotFoundError

        renderer = SuperColliderRenderer(
            table_map=TABLE_MAP, window_registry=NumpyWindowRegistry(),
            samples_dir=str(tmp_path),
            audio_format=AudioFormat('strano', '.xx', 'WAV', 'PCM_U8'),
            sc_config={'synthdef_dir': str(tmp_path)},
        )
        with pytest.raises(ConfigError) as exc:
            with patch('pge.rendering.supercollider_renderer.subprocess.run',
                       return_value=ok()):
                renderer.render_single_stream(FakeStream(), '/out/x.xx')

        assert not isinstance(exc.value, SuperColliderNotFoundError)
        msg = exc.value.user_message()
        assert 'PCM_U8' in msg
        assert 'int24' in msg or 'float' in msg




class TestErrors:

    def test_exit_code_diventa_SuperColliderRenderError(self, renderer):
        from pge.shared.exceptions import (
            EngineError, EngineRuntimeError, SuperColliderRenderError,
        )

        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   return_value=MagicMock(returncode=1, stdout='',
                                          stderr='ERROR: buffer non allocato')):
            with pytest.raises(SuperColliderRenderError) as exc:
                renderer.render_single_stream(FakeStream(), '/out/x.aif')

        err = exc.value
        assert isinstance(err, EngineRuntimeError)
        assert isinstance(err, EngineError)
        assert isinstance(err, RuntimeError)
        assert err.returncode == 1
        msg = err.user_message()
        assert '[ERRORE]' in msg
        assert 'exit code 1' in msg
        assert 'buffer non allocato' in msg

    def test_scsynth_assente_e_un_errore_azionabile(self, renderer):
        from pge.shared.exceptions import SuperColliderNotFoundError

        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   side_effect=FileNotFoundError()):
            with pytest.raises(SuperColliderNotFoundError) as exc:
                renderer.render_single_stream(FakeStream(), '/out/x.aif')
        assert 'scsynth' in exc.value.user_message()

    def test_scsynth_assente_non_e_un_FileNotFoundError(self, renderer):
        """La CLI intercetta FileNotFoundError per dire 'file YAML non
        trovato': un binario mancante che passasse di li' verrebbe
        annunciato come un file di configurazione inesistente."""
        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   side_effect=FileNotFoundError()):
            with pytest.raises(Exception) as exc:
                renderer.render_single_stream(FakeStream(), '/out/x.aif')
        assert not isinstance(exc.value, FileNotFoundError)

    def test_scsynth_a_zero_ma_scritto_su_stderr_non_e_un_errore(self, renderer):
        """scsynth chiacchiera su stderr anche quando va tutto bene."""
        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   return_value=MagicMock(returncode=0, stdout='',
                                          stderr='SC_AudioDriver: ...')):
            assert renderer.render_single_stream(
                FakeStream(), '/out/x.aif') == '/out/x.aif'


# =============================================================================
# 8. CACHE
# =============================================================================

class TestCache:

    @pytest.fixture
    def cached(self, tmp_path, synthdef_file):
        cache = MagicMock()
        renderer = SuperColliderRenderer(
            table_map=TABLE_MAP, window_registry=NumpyWindowRegistry(),
            samples_dir=str(tmp_path), cache_manager=cache,
            stream_data_map={'s1': {'stream_id': 's1'}},
            sc_config={'synthdef_dir': str(tmp_path)},
        )
        return renderer, cache

    def test_stream_clean_non_renderizza(self, cached):
        renderer, cache = cached
        cache.is_dirty.return_value = False
        with patch('pge.rendering.supercollider_renderer.subprocess.run') as run:
            got = renderer.render_single_stream(FakeStream(), '/out/x.aif')
        assert got == '/out/x.aif'
        run.assert_not_called()

    def test_stream_dirty_renderizza_e_aggiorna(self, cached):
        renderer, cache = cached
        cache.is_dirty.return_value = True
        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   return_value=ok()):
            renderer.render_single_stream(FakeStream(), '/out/x.aif')
        cache.update_after_build.assert_called_once()

    def test_render_fallito_non_aggiorna_la_cache(self, cached):
        from pge.shared.exceptions import SuperColliderRenderError

        renderer, cache = cached
        cache.is_dirty.return_value = True
        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   return_value=MagicMock(returncode=1, stdout='', stderr='x')):
            with pytest.raises(SuperColliderRenderError):
                renderer.render_single_stream(FakeStream(), '/out/x.aif')
        cache.update_after_build.assert_not_called()

    def test_stream_fuori_dal_data_map_non_passa_dalla_cache(self, cached):
        renderer, cache = cached
        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   return_value=ok()) as run:
            renderer.render_single_stream(FakeStream('ignoto'), '/out/x.aif')
        cache.is_dirty.assert_not_called()
        run.assert_called_once()


# =============================================================================
# 9. FACTORY
# =============================================================================

class TestFactory:

    def test_crea_il_renderer(self, tmp_path):
        renderer = RendererFactory.create(
            'supercollider',
            table_map=TABLE_MAP,
            window_registry=NumpyWindowRegistry(),
            samples_dir=str(tmp_path),
        )
        assert isinstance(renderer, SuperColliderRenderer)

    def test_e_nei_tipi_validi(self):
        assert 'supercollider' in RendererFactory.available_types()

    def test_i_tipi_validi_sono_ordinati(self):
        """La lista finisce nei messaggi d'errore: un ordine stabile la rende
        confrontabile fra una run e l'altra."""
        tipi = RendererFactory.available_types()
        assert tipi == sorted(tipi)

    def test_errore_su_tipo_ignoto_elenca_supercollider(self):
        from pge.shared.exceptions import InvalidRendererError

        with pytest.raises(InvalidRendererError) as exc:
            RendererFactory.create('bogus')
        assert 'supercollider' in exc.value.available
