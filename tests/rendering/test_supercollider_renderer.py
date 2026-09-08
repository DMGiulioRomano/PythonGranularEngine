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


@pytest.fixture(autouse=True)
def sample_file(tmp_path):
    """Il sample di TABLE_MAP, su disco: lo score writer verifica che i
    sample esistano prima di metterne il path nello score."""
    path = tmp_path / "pino.wav"
    path.write_bytes(b'RIFF')
    return path


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


def run_ok(cmd, **kwargs):
    """subprocess.run finto che si comporta come i binari veri.

    scsynth scrive il file di output: senza, il controllo post-render lo
    vedrebbe mancante e solleverebbe -- che e' esattamente il suo lavoro
    (scsynth esce 0 anche quando non ha reso niente).
    """
    if '-N' in cmd:
        with open(cmd[cmd.index('-N') + 3], 'wb') as f:
            f.write(b'\0' * 64)
    return ok()


class FakePopen:
    """sclang finto, con i due comportamenti che conta distinguere.

    `esce=True` e' Linux: lo script scrive la SynthDef e il processo termina.
    `esce=False` e' macOS, dove `0.exit` non chiude sclang: il file c'e' ma il
    processo resta dentro l'event loop di Cocoa, vivo e inerte. Il renderer
    deve considerare finita la compilazione nel secondo caso come nel primo --
    aspettare il codice d'uscita significherebbe aspettare il timeout per un
    lavoro gia' fatto.
    """

    def __init__(self, scrive=None, returncode=0, stdout='', stderr='',
                 esce=True):
        if scrive is not None:
            with open(scrive, 'wb') as f:
                f.write(b'COMPILATO')
        self._esce = esce
        self.returncode = returncode if esce else None
        self._stdout, self._stderr = stdout, stderr
        self.terminato = False
        self.ucciso = False

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        if not self._esce and not self.terminato:
            raise subprocess.TimeoutExpired(cmd='sclang', timeout=timeout)
        self.returncode = self.returncode or 0
        return self.returncode

    def communicate(self):
        return self._stdout, self._stderr

    def terminate(self):
        self.terminato = True
        self.returncode = 0

    def kill(self):
        self.ucciso = True
        self.returncode = -9


def popen_che(creati=None, **kwargs):
    """side_effect per patchare subprocess.Popen con un FakePopen.

    Il FakePopen si costruisce alla chiamata, non prima: costruirlo in
    anticipo scriverebbe il .scsyndef mentre il renderer ancora decide se
    ricompilare, e il ramo sotto esame non verrebbe nemmeno percorso.
    """
    def _fabbrica(cmd, **_):
        proc = FakePopen(**kwargs)
        if creati is not None:
            creati.append(proc)
        return proc
    return _fabbrica


@pytest.fixture
def out_aif(tmp_path):
    return str(tmp_path / "x.aif")


@pytest.fixture
def out_mix(tmp_path):
    return str(tmp_path / "mix.aif")


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

        with patch('pge.rendering.supercollider_renderer.subprocess.Popen',
                   side_effect=popen_che(
                       scrive=out / "pgeGrain.scsyndef")) as run:
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

        with patch('pge.rendering.supercollider_renderer.subprocess.Popen',
                   side_effect=popen_che(scrive=compiled)):
            assert renderer.synthdef_bytes() == b'COMPILATO'

    def test_compila_una_volta_sola(self, tmp_path):
        source = tmp_path / "pge_grain.scd"
        source.write_text("// sorgente")

        renderer = SuperColliderRenderer(
            table_map=TABLE_MAP, window_registry=NumpyWindowRegistry(),
            samples_dir=str(tmp_path),
            sc_config={'synthdef_source': str(source),
                       'synthdef_dir': str(tmp_path)},
        )

        with patch('pge.rendering.supercollider_renderer.subprocess.Popen',
                   side_effect=popen_che(
                       scrive=tmp_path / "pgeGrain.scsyndef")) as run:
            renderer.synthdef_bytes()
            renderer.synthdef_bytes()
        assert run.call_count == 1

    def test_sclang_gira_headless(self, tmp_path, monkeypatch):
        """sclang su Debian/Ubuntu e' linkato a Qt: senza un display aborta
        con SIGABRT (`qt.qpa.xcb: could not connect to display`) prima di
        eseguire una riga dello script. Su un runner CI, o su un server, e'
        la condizione normale -- non un caso limite."""
        monkeypatch.setattr(
            'pge.rendering.supercollider_renderer.sys.platform', 'linux')
        monkeypatch.delenv('QT_QPA_PLATFORM', raising=False)
        source = tmp_path / "pge_grain.scd"
        source.write_text("// sorgente")

        renderer = SuperColliderRenderer(
            table_map=TABLE_MAP, window_registry=NumpyWindowRegistry(),
            samples_dir=str(tmp_path),
            sc_config={'synthdef_source': str(source),
                       'synthdef_dir': str(tmp_path)},
        )

        with patch('pge.rendering.supercollider_renderer.subprocess.Popen',
                   side_effect=popen_che(
                       scrive=tmp_path / "pgeGrain.scsyndef")) as run:
            renderer.synthdef_bytes()

        assert run.call_args.kwargs['env']['QT_QPA_PLATFORM'] == 'offscreen'

    def test_su_macos_niente_offscreen(self, tmp_path, monkeypatch):
        """Il rimedio a un guasto non deve essere lo stesso guasto sull'altra
        piattaforma: il bundle SuperCollider.app spedisce il solo plugin
        `cocoa`, e chiedere `offscreen` fa abortire sclang con SIGABRT
        esattamente come il display mancante lo fa abortire su Linux."""
        monkeypatch.setattr(
            'pge.rendering.supercollider_renderer.sys.platform', 'darwin')
        monkeypatch.delenv('QT_QPA_PLATFORM', raising=False)
        source = tmp_path / "pge_grain.scd"
        source.write_text("// sorgente")

        renderer = SuperColliderRenderer(
            table_map=TABLE_MAP, window_registry=NumpyWindowRegistry(),
            samples_dir=str(tmp_path),
            sc_config={'synthdef_source': str(source),
                       'synthdef_dir': str(tmp_path)},
        )

        with patch('pge.rendering.supercollider_renderer.subprocess.Popen',
                   side_effect=popen_che(
                       scrive=tmp_path / "pgeGrain.scsyndef")) as run:
            renderer.synthdef_bytes()

        assert 'QT_QPA_PLATFORM' not in run.call_args.kwargs['env']

    def test_una_scelta_esplicita_di_piattaforma_qt_vince(self, tmp_path,
                                                          monkeypatch):
        """Chi ha un display e lo vuole usare non deve essere scavalcato: il
        default vale come default, non come imposizione."""
        monkeypatch.setattr(
            'pge.rendering.supercollider_renderer.sys.platform', 'linux')
        monkeypatch.setenv('QT_QPA_PLATFORM', 'xcb')
        source = tmp_path / "pge_grain.scd"
        source.write_text("// sorgente")

        renderer = SuperColliderRenderer(
            table_map=TABLE_MAP, window_registry=NumpyWindowRegistry(),
            samples_dir=str(tmp_path),
            sc_config={'synthdef_source': str(source),
                       'synthdef_dir': str(tmp_path)},
        )

        with patch('pge.rendering.supercollider_renderer.subprocess.Popen',
                   side_effect=popen_che(
                       scrive=tmp_path / "pgeGrain.scsyndef")) as run:
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

        with patch('pge.rendering.supercollider_renderer.subprocess.Popen',
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
        with patch('pge.rendering.supercollider_renderer.subprocess.Popen',
                   side_effect=popen_che(returncode=1,
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
        with patch('pge.rendering.supercollider_renderer.subprocess.Popen',
                   side_effect=popen_che()):
            with pytest.raises(SuperColliderRenderError):
                renderer.synthdef_bytes()

    def test_sclang_che_non_esce_ma_scrive_e_riuscito(self, tmp_path):
        """Su macOS `0.exit` non chiude sclang: lo script scrive la SynthDef
        in un secondo e poi il processo resta dentro l'event loop di Cocoa
        (`-[NSApplication run]`), vivo e inerte.

        Il risultato di questo passo e' il file, non il codice d'uscita:
        aspettare il secondo significherebbe aspettare il timeout a ogni
        compilazione, per un lavoro gia' finito -- un blocco travestito da
        attesa. Trovato facendo girare l'e2e su macOS, dove ogni build
        restava appesa.
        """
        source = tmp_path / "pge_grain.scd"
        source.write_text("// sorgente")
        renderer = SuperColliderRenderer(
            table_map=TABLE_MAP, window_registry=NumpyWindowRegistry(),
            samples_dir=str(tmp_path),
            sc_config={'synthdef_source': str(source),
                       'synthdef_dir': str(tmp_path),
                       'compile_timeout': 5},
        )
        creati = []

        with patch('pge.rendering.supercollider_renderer.subprocess.Popen',
                   side_effect=popen_che(
                       creati, scrive=tmp_path / "pgeGrain.scsyndef",
                       esce=False)):
            assert renderer.synthdef_bytes() == b'COMPILATO'

        assert creati[0].terminato, (
            "il processo appeso va chiuso, non lasciato li'")

    def test_sclang_che_non_scrive_nulla_va_in_timeout(self, tmp_path):
        """L'attesa finisce col file; se il file non arriva mai e nemmeno il
        processo esce, resta il timeout -- corto, perche' scrivere una
        SynthDef e' lavoro di un secondo."""
        from pge.shared.exceptions import SuperColliderRenderError

        source = tmp_path / "pge_grain.scd"
        source.write_text("// non scrive e non esce")
        renderer = SuperColliderRenderer(
            table_map=TABLE_MAP, window_registry=NumpyWindowRegistry(),
            samples_dir=str(tmp_path),
            sc_config={'synthdef_source': str(source),
                       'synthdef_dir': str(tmp_path),
                       'compile_timeout': 0.2},
        )
        creati = []

        with patch('pge.rendering.supercollider_renderer.subprocess.Popen',
                   side_effect=popen_che(creati, esce=False)):
            with pytest.raises(SuperColliderRenderError) as exc:
                renderer.synthdef_bytes()
        assert 'non ha scritto' in str(exc.value)
        assert creati[0].ucciso


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

    def test_api_e_cli_non_ricopiano_i_default(self):
        """Un default scritto in piu' posti sono piu' comportamenti che
        possono divergere: API e CLI dicono None e il renderer decide."""
        from pge.api import SuperColliderOptions
        opts = SuperColliderOptions()
        assert (opts.synthdef_source, opts.synthdef_dir,
                opts.block_size, opts.max_nodes) == (None, None, None, None)

    def test_il_renderer_applica_i_suoi_default(self, tmp_path, synthdef_file,
                                                out_aif):
        """None all'ingresso non significa None nel comando."""
        import pge.api as api
        from pge.rendering.supercollider_renderer import (
            DEFAULT_BLOCK_SIZE, DEFAULT_MAX_NODES,
        )
        renderer = SuperColliderRenderer(
            table_map=TABLE_MAP, window_registry=NumpyWindowRegistry(),
            samples_dir=str(tmp_path),
            sc_config={k: v for k, v in {
                'synthdef_dir': str(tmp_path),
                'block_size': api.SuperColliderOptions().block_size,
                'max_nodes': api.SuperColliderOptions().max_nodes,
            }.items() if v is not None},
        )
        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   side_effect=run_ok) as run:
            renderer.render_single_stream(FakeStream(), out_aif)
        cmd = run.call_args.args[0]
        assert cmd[cmd.index('-z') + 1] == str(DEFAULT_BLOCK_SIZE)
        assert cmd[cmd.index('-n') + 1] == str(DEFAULT_MAX_NODES)

# =============================================================================
# 3. RIGA DI COMANDO
# =============================================================================

class TestCommand:

    def _cmd(self, renderer, output):
        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   side_effect=run_ok) as run:
            renderer.render_single_stream(FakeStream(), output)
        return run.call_args.args[0]

    def test_forma_generale(self, renderer, out_aif):
        cmd = self._cmd(renderer, out_aif)
        assert cmd[0].endswith('scsynth')
        # I 6 argomenti posizionali di -N, nell'ordine imposto da scsynth.
        i = cmd.index('-N')
        assert cmd[i + 1].endswith('.osc')
        assert cmd[i + 2] == '_'                 # nessun file di input
        assert cmd[i + 3] == out_aif
        assert cmd[i + 4] == '48000'
        assert cmd[i + 5] == 'AIFF'
        assert cmd[i + 6] == 'float'

    def test_le_opzioni_precedono_N(self, renderer, out_aif):
        """scsynth interpreta come posizionali tutto cio' che segue -N."""
        cmd = self._cmd(renderer, out_aif)
        i = cmd.index('-N')
        assert '-o' in cmd[:i] and '-z' in cmd[:i]

    def test_due_canali_di_uscita_zero_di_ingresso(self, renderer, out_aif):
        cmd = self._cmd(renderer, out_aif)
        assert cmd[cmd.index('-o') + 1] == '2'
        assert cmd[cmd.index('-i') + 1] == '0'

    def test_block_size_uno_per_default(self, renderer, out_aif):
        """Onset campione-accurati: e' la stessa scelta di main.orc, che gira
        a ksmps=1 (sr=kr=48000). Con il block size di default gli onset si
        quantizzerebbero a 1.33 ms, che nella sintesi granulare non e' un
        dettaglio."""
        cmd = self._cmd(renderer, out_aif)
        assert cmd[cmd.index('-z') + 1] == '1'

    def test_max_nodes_configurabile(self, tmp_path, synthdef_file, out_aif):
        """E' il limite che il commento descrive come quello che fa morire il
        render a meta': deve essere raggiungibile senza passare dall'API
        (review PR #240, punto 4)."""
        renderer = SuperColliderRenderer(
            table_map=TABLE_MAP, window_registry=NumpyWindowRegistry(),
            samples_dir=str(tmp_path),
            sc_config={'synthdef_dir': str(tmp_path), 'max_nodes': 4096},
        )
        cmd = self._cmd(renderer, out_aif)
        assert cmd[cmd.index('-n') + 1] == '4096'

    def test_block_size_configurabile(self, tmp_path, synthdef_file, out_aif):
        renderer = SuperColliderRenderer(
            table_map=TABLE_MAP, window_registry=NumpyWindowRegistry(),
            samples_dir=str(tmp_path),
            sc_config={'synthdef_dir': str(tmp_path), 'block_size': 64},
        )
        cmd = self._cmd(renderer, out_aif)
        assert cmd[cmd.index('-z') + 1] == '64'

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
            cmd = self._cmd(
                renderer,
                str(tmp_path / f'x{FORMATS[label].extension}'))
            i = cmd.index('-N')
            assert cmd[i + 5] == header
            assert cmd[i + 6] == sample_format

    def test_sample_rate_dal_renderer(self, tmp_path, synthdef_file, out_aif):
        renderer = SuperColliderRenderer(
            table_map=TABLE_MAP, window_registry=NumpyWindowRegistry(),
            samples_dir=str(tmp_path), output_sr=96000,
            sc_config={'synthdef_dir': str(tmp_path)},
        )
        cmd = self._cmd(renderer, out_aif)
        assert cmd[cmd.index('-N') + 4] == '96000'


# =============================================================================
# 4. STEMS
# =============================================================================

class TestRenderSingleStream:

    def test_ritorna_il_path(self, renderer, out_aif):
        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   side_effect=run_ok):
            got = renderer.render_single_stream(FakeStream(), out_aif)
        assert got == out_aif

    def test_score_scritto_e_poi_rimosso(self, renderer, out_aif):
        visto = {}

        def spia(cmd, **kwargs):
            path = cmd[cmd.index('-N') + 1]
            visto['path'] = path
            visto['esisteva'] = os.path.exists(path)
            return run_ok(cmd)

        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   side_effect=spia):
            renderer.render_single_stream(FakeStream(), out_aif)

        assert visto['esisteva'], "lo score deve esistere quando scsynth parte"
        assert not os.path.exists(visto['path']), "temporaneo non ripulito"

    def test_onset_relativi(self, renderer, out_aif):
        """STEMS: lo stream parte da zero nel proprio file."""
        from tests.rendering.test_osc import decode_nrt

        stream = FakeStream(onset=5.0, duration=1.0, voices=[[grain(5.5)]])
        catturato = {}

        def spia(cmd, **kwargs):
            path = cmd[cmd.index('-N') + 1]
            with open(path, 'rb') as f:
                catturato['bundles'] = decode_nrt(f.read())
            return run_ok(cmd)

        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   side_effect=spia):
            renderer.render_single_stream(stream, out_aif)

        tempi = [t for t, elements in catturato['bundles']
                 for addr, _ in elements if addr == '/s_new']
        assert tempi == [pytest.approx(0.5)]

    def test_lo_score_contiene_la_synthdef_compilata(self, renderer, out_aif):
        from tests.rendering.test_osc import decode_nrt

        catturato = {}

        def spia(cmd, **kwargs):
            with open(cmd[cmd.index('-N') + 1], 'rb') as f:
                catturato['bundles'] = decode_nrt(f.read())
            return run_ok(cmd)

        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   side_effect=spia):
            renderer.render_single_stream(FakeStream(), out_aif)

        blob = [args[0] for _, elements in catturato['bundles']
                for addr, args in elements if addr == '/d_recv']
        assert blob == [b'SCgf-FAKE-DEF']


# =============================================================================
# 5. MIX
# =============================================================================

class TestRenderMergedStreams:

    def test_ritorna_il_path(self, renderer, out_mix):
        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   side_effect=run_ok):
            got = renderer.render_merged_streams(
                [FakeStream(), FakeStream('s2')], out_mix)
        assert got == out_mix

    def test_onset_assoluti(self, renderer, out_mix):
        from tests.rendering.test_osc import decode_nrt

        s1 = FakeStream('s1', 0.0, 1.0, [[grain(0.5)]])
        s2 = FakeStream('s2', 10.0, 1.0, [[grain(10.5)]])
        catturato = {}

        def spia(cmd, **kwargs):
            with open(cmd[cmd.index('-N') + 1], 'rb') as f:
                catturato['bundles'] = decode_nrt(f.read())
            return run_ok(cmd)

        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   side_effect=spia):
            renderer.render_merged_streams([s1, s2], out_mix)

        tempi = [t for t, elements in catturato['bundles']
                 for addr, _ in elements if addr == '/s_new']
        assert tempi == [pytest.approx(0.5), pytest.approx(10.5)]

    def test_la_cache_non_tocca_il_mix(self, tmp_path, synthdef_file, out_mix):
        """Come in CsoundRenderer: la build incrementale e' per stem."""
        cache = MagicMock()
        renderer = SuperColliderRenderer(
            table_map=TABLE_MAP, window_registry=NumpyWindowRegistry(),
            samples_dir=str(tmp_path), cache_manager=cache,
            stream_data_map={'s1': {'stream_id': 's1'}},
            sc_config={'synthdef_dir': str(tmp_path)},
        )
        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   side_effect=run_ok):
            renderer.render_merged_streams([FakeStream()], out_mix)
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
                   side_effect=run_ok):
            renderer.render_single_stream(
                FakeStream(), str(tmp_path / 'brano__s1.aif'))

        assert (osc_dir / "brano__s1.osc").exists()

    def test_directory_creata_se_manca(self, tmp_path, synthdef_file, out_aif):
        osc_dir = tmp_path / "a" / "b"
        renderer = SuperColliderRenderer(
            table_map=TABLE_MAP, window_registry=NumpyWindowRegistry(),
            samples_dir=str(tmp_path), osc_dir=str(osc_dir),
            sc_config={'synthdef_dir': str(tmp_path)},
        )
        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   side_effect=run_ok):
            renderer.render_single_stream(FakeStream(), out_aif)
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
                       side_effect=run_ok):
                renderer.render_single_stream(FakeStream(), '/out/x.xx')

        assert not isinstance(exc.value, SuperColliderNotFoundError)
        msg = exc.value.user_message()
        assert 'PCM_U8' in msg
        assert 'int24' in msg or 'float' in msg




class TestErrors:

    def test_exit_code_diventa_SuperColliderRenderError(self, renderer, out_aif):
        from pge.shared.exceptions import (
            EngineError, EngineRuntimeError, SuperColliderRenderError,
        )

        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   return_value=MagicMock(returncode=1, stdout='',
                                          stderr='ERROR: buffer non allocato')):
            with pytest.raises(SuperColliderRenderError) as exc:
                renderer.render_single_stream(FakeStream(), out_aif)

        err = exc.value
        assert isinstance(err, EngineRuntimeError)
        assert isinstance(err, EngineError)
        assert isinstance(err, RuntimeError)
        assert err.returncode == 1
        msg = err.user_message()
        assert '[ERRORE]' in msg
        assert 'exit code 1' in msg
        assert 'buffer non allocato' in msg

    def test_scsynth_assente_e_un_errore_azionabile(self, renderer, out_aif):
        from pge.shared.exceptions import SuperColliderNotFoundError

        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   side_effect=FileNotFoundError()):
            with pytest.raises(SuperColliderNotFoundError) as exc:
                renderer.render_single_stream(FakeStream(), out_aif)
        assert 'scsynth' in exc.value.user_message()

    def test_scsynth_assente_non_e_un_FileNotFoundError(self, renderer, out_aif):
        """Per un binario assente il builtin sarebbe falso: il file che
        manca non e' quello che il tipo lascia intendere.

        La ragione scritta qui prima -- «la CLI intercetta FileNotFoundError
        per dire 'file YAML non trovato'» -- e' caduta con la #257, che
        quell'handler lo toglie del tutto; la regola resta, sul valore di
        verita' del tipo (vedi `ConfigFileNotFoundError`, che il builtin lo
        eredita perche' li' dice il vero)."""
        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   side_effect=FileNotFoundError()):
            with pytest.raises(Exception) as exc:
                renderer.render_single_stream(FakeStream(), out_aif)
        assert not isinstance(exc.value, FileNotFoundError)

    def test_scsynth_a_zero_ma_scritto_su_stderr_non_e_un_errore(self, renderer, out_aif):
        """scsynth chiacchiera su stderr anche quando va tutto bene."""
        def chiacchiera(cmd, **kwargs):
            run_ok(cmd)
            return MagicMock(returncode=0, stdout='',
                             stderr='SC_AudioDriver: ...')

        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   side_effect=chiacchiera):
            assert renderer.render_single_stream(
                FakeStream(), out_aif) == out_aif


class TestGuastiSilenziosi:
    """scsynth esce 0 anche quando non ha reso niente.

    Output non apribile, `/b_allocReadChannel` su un sample mancante,
    `/s_new` fallito per nodi o memoria esauriti: tre guasti reali con
    returncode 0. Csound in questi casi esce non-zero e NumPy solleva --
    senza questi controlli il backend nuovo sarebbe l'unico a restituire
    silenzio annunciandolo come suono.
    """

    def test_output_mancante_e_un_errore(self, renderer, out_aif):
        from pge.shared.exceptions import SuperColliderRenderError

        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   return_value=ok()):
            with pytest.raises(SuperColliderRenderError) as exc:
                renderer.render_single_stream(FakeStream(), out_aif)
        assert out_aif in str(exc.value)

    def test_output_vuoto_e_un_errore(self, renderer, out_aif):
        from pge.shared.exceptions import SuperColliderRenderError

        def vuoto(cmd, **kwargs):
            open(cmd[cmd.index('-N') + 3], 'wb').close()
            return ok()

        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   side_effect=vuoto):
            with pytest.raises(SuperColliderRenderError):
                renderer.render_single_stream(FakeStream(), out_aif)

    @pytest.mark.parametrize('riga', [
        'FAILURE IN SERVER /b_allocReadChannel File could not be opened',
        "Couldn't open non real time output file '/out/x.aif'",
        'alloc failed, increase server memory allocation',
        'exception in GraphDef_Recv: alloc failed',
    ])
    def test_i_guasti_riportati_a_parole_sono_errori(self, renderer, out_aif,
                                                     riga):
        """Il file c'e' ma scsynth ha detto che qualcosa e' andato storto."""
        from pge.shared.exceptions import SuperColliderRenderError

        def guasto(cmd, **kwargs):
            run_ok(cmd)
            return MagicMock(returncode=0, stdout=riga, stderr='')

        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   side_effect=guasto):
            with pytest.raises(SuperColliderRenderError) as exc:
                renderer.render_single_stream(FakeStream(), out_aif)
        assert riga in exc.value.user_message()

    def test_timeout_e_un_errore_non_un_blocco(self, renderer, out_aif):
        """sclang che non arriva a `0.exit` resta vivo col suo event loop, e
        con capture_output=True la pipe non mostra niente: senza timeout
        `make all` si pianta muto."""
        from pge.shared.exceptions import SuperColliderRenderError

        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   side_effect=subprocess.TimeoutExpired(cmd='scsynth',
                                                         timeout=1)):
            with pytest.raises(SuperColliderRenderError) as exc:
                renderer.render_single_stream(FakeStream(), out_aif)
        assert 'non ha terminato' in str(exc.value)

    def test_il_timeout_e_configurabile(self, tmp_path, synthdef_file,
                                        out_aif):
        renderer = SuperColliderRenderer(
            table_map=TABLE_MAP, window_registry=NumpyWindowRegistry(),
            samples_dir=str(tmp_path),
            sc_config={'synthdef_dir': str(tmp_path), 'timeout': 7},
        )
        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   side_effect=run_ok) as run:
            renderer.render_single_stream(FakeStream(), out_aif)
        assert run.call_args.kwargs['timeout'] == 7

    def test_lo_stdout_finisce_nel_messaggio_di_errore(self, renderer,
                                                       out_aif):
        """sclang posta i propri errori su stdout, non su stderr: senza,
        un refuso nella SynthDef arriva con la sola riga dell'exit code."""
        from pge.shared.exceptions import SuperColliderRenderError

        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   return_value=MagicMock(
                       returncode=1,
                       stdout=("compiling class library...\n"
                               "ERROR: Parse error in file pge_grain.scd"),
                       stderr='')):
            with pytest.raises(SuperColliderRenderError) as exc:
                renderer.render_single_stream(FakeStream(), out_aif)
        assert 'Parse error' in exc.value.user_message()


class TestMemoriaRealTime:
    """`-n` da solo non basta: il Graph di ogni /s_new esce dal pool `-m`,
    che al default di 8192 KB si esaurisce molto prima dei nodi -- e si
    esaurisce con `alloc failed`, nodo non creato, exit 0."""

    def _cmd(self, renderer, output):
        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   side_effect=run_ok) as run:
            renderer.render_single_stream(FakeStream(), output)
        return run.call_args.args[0]

    def test_il_pool_cresce_coi_nodi(self, renderer, out_aif):
        cmd = self._cmd(renderer, out_aif)
        assert cmd[cmd.index('-m') + 1] == cmd[cmd.index('-n') + 1]

    def test_non_scende_sotto_il_default_di_scsynth(self, tmp_path,
                                                    synthdef_file, out_aif):
        renderer = SuperColliderRenderer(
            table_map=TABLE_MAP, window_registry=NumpyWindowRegistry(),
            samples_dir=str(tmp_path),
            sc_config={'synthdef_dir': str(tmp_path), 'max_nodes': 16},
        )
        cmd = self._cmd(renderer, out_aif)
        assert cmd[cmd.index('-m') + 1] == '8192'


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

    def test_stream_clean_non_renderizza(self, cached, out_aif):
        renderer, cache = cached
        cache.is_dirty.return_value = False
        with patch('pge.rendering.supercollider_renderer.subprocess.run') as run:
            got = renderer.render_single_stream(FakeStream(), out_aif)
        assert got == out_aif
        run.assert_not_called()

    def test_stream_dirty_renderizza_e_aggiorna(self, cached, out_aif):
        renderer, cache = cached
        cache.is_dirty.return_value = True
        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   side_effect=run_ok):
            renderer.render_single_stream(FakeStream(), out_aif)
        cache.update_after_build.assert_called_once()

    def test_render_fallito_non_aggiorna_la_cache(self, cached, out_aif):
        from pge.shared.exceptions import SuperColliderRenderError

        renderer, cache = cached
        cache.is_dirty.return_value = True
        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   return_value=MagicMock(returncode=1, stdout='', stderr='x')):
            with pytest.raises(SuperColliderRenderError):
                renderer.render_single_stream(FakeStream(), out_aif)
        cache.update_after_build.assert_not_called()

    def test_stream_fuori_dal_data_map_non_passa_dalla_cache(self, cached, out_aif):
        renderer, cache = cached
        with patch('pge.rendering.supercollider_renderer.subprocess.run',
                   side_effect=run_ok) as run:
            renderer.render_single_stream(FakeStream('ignoto'), out_aif)
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
