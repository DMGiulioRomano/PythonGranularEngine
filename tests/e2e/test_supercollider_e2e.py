# tests/e2e/test_supercollider_e2e.py
"""
Test end-to-end per il backend SuperCollider (issue #228).

Invoca `make all RENDERER=supercollider` come subprocess e verifica che la
catena Make -> Python -> score .osc -> scsynth -> filesystem produca audio.

E' l'unico posto in cui il grafo della SynthDef viene davvero eseguito: i
test unitari e quello di integrazione coprono tutto cio' che sta prima del
subprocess, ma non possono dire se `pge_grain.scd` suona. Se questo file
salta, quella parte non e' verificata.

Scenari:
1. TestSuperColliderMix   - STEMS=false: un file unico, non silenzioso
2. TestSuperColliderStems - STEMS=true: un file per stream
3. TestKeepOsc            - KEEP_OSC=true: lo score resta ispezionabile
4. TestParitaConNumpy     - stesso YAML sui due backend: stessa forma

Requisiti:
  - supercollider (scsynth + sclang) nel PATH
  - .venv configurato (make venv-setup)

Esegui con:
  make e2e-tests
  oppure: pytest tests/e2e/test_supercollider_e2e.py -m e2e -v
"""

import os
import shutil
import subprocess

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("scsynth") is None or shutil.which("sclang") is None,
    reason="SuperCollider non disponibile (serve scsynth + sclang)",
)

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..')
)

# Il campione di prova non e' un tono stazionario, ed e' una scelta.
# Con un seno costante la posizione di lettura del grano non si vede in
# nessuna misura d'ampiezza: leggere dal punto sbagliato darebbe la stessa
# curva RMS, e il confronto con NumPy passerebbe anche con il puntatore
# rotto. Una rampa d'ampiezza decrescente rende la posizione di lettura
# osservabile: il grano che legge piu' avanti nel file suona piu' piano.
PROBE_SAMPLE = "e2e_sc_probe.wav"
PROBE_DUR_SEC = 3.0

_YAML = """\
composition:
  title: "e2e supercollider"

seed: 11

streams:
  - stream_id: "s1"
    onset: 0.0
    duration: 1.0
    sample: "%s"
    density: 20
    pointer:
      speed: 1.0
    grain:
      duration: 0.05
      envelope: "hanning"
  - stream_id: "s2"
    onset: 1.0
    duration: 1.0
    sample: "%s"
    density: 20
    pointer:
      speed: 1.0
    grain:
      duration: 0.05
      envelope: "hanning"
""" % (PROBE_SAMPLE, PROBE_SAMPLE)


# Stream che legge una zona precisa della sonda, lontana dall'inizio. Serve al
# test della posizione di lettura: la` la sonda vale ~1/3 dell'ampiezza che ha
# a zero, quindi un grano che legge dal punto sbagliato si vede come un fattore
# tre sul picco, non come una sfumatura.
READ_START_SEC = 2.0

_YAML_READ_POS = """\
composition:
  title: "e2e supercollider - posizione di lettura"

seed: 3

streams:
  - stream_id: "fisso"
    onset: 0.0
    duration: 1.0
    sample: "%s"
    density: 10
    pointer:
      start: %s
      speed: 0.0
    grain:
      duration: 0.05
      envelope: "hanning"
""" % (PROBE_SAMPLE, READ_START_SEC)


# =============================================================================
# HELPERS
# =============================================================================

@pytest.fixture(scope="module", autouse=True)
def probe_sample():
    """Scrive il campione di prova in refs/ e lo rimuove alla fine.

    Sta in refs/ e non in tmp_path perche' e' la sample dir che i renderer
    usano di default, la stessa per i tre backend. Il file e' generato qui
    invece di dipendere da refs/pino.wav (che esiste solo in CI): un test che
    salta per un file mancante non verifica niente.
    """
    import numpy as np
    import soundfile as sf

    sr = 48000
    n = int(PROBE_DUR_SEC * sr)
    t = np.arange(n) / sr
    # Seno a 440 Hz con ampiezza che decresce linearmente: l'ampiezza dice
    # da dove si sta leggendo.
    audio = (np.sin(2 * np.pi * 440 * t) * (1.0 - t / PROBE_DUR_SEC))

    refs = os.path.join(PROJECT_ROOT, "refs")
    os.makedirs(refs, exist_ok=True)
    path = os.path.join(refs, PROBE_SAMPLE)
    sf.write(path, audio.astype("float32"), sr)
    yield path
    if os.path.exists(path):
        os.remove(path)


def _make_build(tmp_path, renderer='supercollider', stems=False, extra=(),
                yaml_text=None):
    """Invoca `make all` con directory temporanee. Ritorna (proc, output)."""
    sfdir = tmp_path / "output"
    logdir = tmp_path / "logs"
    ymldir = tmp_path / "configs"
    cachedir = tmp_path / "cache"
    gendir = tmp_path / "generated"

    for d in (sfdir, logdir, ymldir, cachedir, gendir):
        d.mkdir(exist_ok=True)
    (ymldir / "e2e_sc_test.yml").write_text(yaml_text or _YAML)

    cmd = [
        'make', 'all',
        'FILE=e2e_sc_test',
        f'RENDERER={renderer}',
        f'STEMS={"true" if stems else "false"}',
        'CACHE=false',
        'AUTOKILL=false', 'AUTOPEN=false', 'AUTOVISUAL=false',
        'SHOWSTATIC=false', 'PRECLEAN=false', 'REAPER=false',
        f'SFDIR={sfdir}', f'LOGDIR={logdir}', f'YMLDIR={ymldir}',
        f'CACHEDIR={cachedir}', f'GENDIR={gendir}',
        f'SC_SYNTHDEF_DIR={gendir}',
        *extra,
    ]
    proc = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
    return proc, (proc.stdout or '') + (proc.stderr or '')


def _peak(path):
    """Picco assoluto del file audio, per distinguere il suono dal silenzio."""
    import numpy as np
    import soundfile as sf
    audio, _ = sf.read(str(path))
    return float(np.max(np.abs(audio))) if audio.size else 0.0


# =============================================================================
# 1. MIX
# =============================================================================

@pytest.mark.e2e
class TestSuperColliderMix:

    def test_build_riuscita(self, tmp_path):
        proc, output = _make_build(tmp_path)
        assert proc.returncode == 0, f"make fallito:\n{output}"

    def test_produce_un_file_audio(self, tmp_path):
        _make_build(tmp_path)
        assert (tmp_path / "output" / "e2e_sc_test.aif").exists()

    def test_il_file_non_e_silenzio(self, tmp_path):
        """Uno score sintatticamente valido che non produce campioni e' il
        modo piu' facile di sbagliare questo backend: il file esiste, dura
        il giusto e non contiene niente."""
        _make_build(tmp_path)
        assert _peak(tmp_path / "output" / "e2e_sc_test.aif") > 1e-4

    def test_durata_copre_i_due_stream(self, tmp_path):
        import soundfile as sf

        _make_build(tmp_path)
        info = sf.info(str(tmp_path / "output" / "e2e_sc_test.aif"))
        assert info.duration == pytest.approx(2.0, abs=0.15)

    def test_stereo(self, tmp_path):
        import soundfile as sf

        _make_build(tmp_path)
        assert sf.info(str(tmp_path / "output" / "e2e_sc_test.aif")).channels == 2

    def test_synthdef_compilata(self, tmp_path):
        """Il .scsyndef e' un artefatto di build: il renderer lo produce da
        solo alla prima necessita'."""
        _make_build(tmp_path)
        assert (tmp_path / "generated" / "pgeGrain.scsyndef").exists()


# =============================================================================
# 2. STEMS
# =============================================================================

@pytest.mark.e2e
class TestSuperColliderStems:

    def test_un_file_per_stream(self, tmp_path):
        proc, output = _make_build(tmp_path, stems=True)
        assert proc.returncode == 0, f"make fallito:\n{output}"
        sfdir = tmp_path / "output"
        assert (sfdir / "e2e_sc_test__s1.aif").exists()
        assert (sfdir / "e2e_sc_test__s2.aif").exists()

    def test_ogni_stem_suona(self, tmp_path):
        _make_build(tmp_path, stems=True)
        for name in ("e2e_sc_test__s1.aif", "e2e_sc_test__s2.aif"):
            assert _peak(tmp_path / "output" / name) > 1e-4, name

    def test_lo_stem_parte_da_zero(self, tmp_path):
        """s2 ha onset 1.0 ma nel proprio file dura 1 secondo e comincia
        subito, come negli altri due backend."""
        import soundfile as sf

        _make_build(tmp_path, stems=True)
        info = sf.info(str(tmp_path / "output" / "e2e_sc_test__s2.aif"))
        assert info.duration == pytest.approx(1.0, abs=0.15)


# =============================================================================
# 3. KEEP-OSC
# =============================================================================

@pytest.mark.e2e
class TestKeepOsc:

    def test_score_conservato(self, tmp_path):
        _make_build(tmp_path, extra=('KEEP_OSC=true',))
        assert (tmp_path / "generated" / "e2e_sc_test.osc").exists()

    def test_score_assente_di_default(self, tmp_path):
        _make_build(tmp_path)
        assert not (tmp_path / "generated" / "e2e_sc_test.osc").exists()


# =============================================================================
# 4. POSIZIONE DI LETTURA
# =============================================================================

@pytest.mark.e2e
class TestPosizioneDiLettura:
    """Il grano legge dalla posizione che lo score dichiara, non dall'inizio
    del file.

    E' il test che serviva e che all'inizio non c'era: la prima versione della
    SynthDef passava l'offset a `Phasor` come `resetPos`, che senza un trigger
    non viene mai usato -- ogni grano leggeva da zero. Il suono c'era comunque,
    il file durava il giusto, i picchi erano nello stesso ordine di grandezza:
    solo il materiale era quello sbagliato. Una misura statistica lo vedeva
    appena (correlazione RMS 0.65); questa lo vede come un fattore tre.

    Il confronto e' con NumPy sullo stesso YAML, non con un numero scritto a
    mano: la posizione giusta e' quella che dice il motore.
    """

    def _render_both(self, tmp_path):
        sc_dir = tmp_path / "sc"
        np_dir = tmp_path / "np"
        sc_dir.mkdir()
        np_dir.mkdir()
        _make_build(sc_dir, renderer='supercollider', yaml_text=_YAML_READ_POS)
        _make_build(np_dir, renderer='numpy', yaml_text=_YAML_READ_POS)
        return (sc_dir / "output" / "e2e_sc_test.aif",
                np_dir / "output" / "e2e_sc_test.aif")

    def test_picchi_quasi_uguali(self, tmp_path):
        sc_peak, np_peak = (_peak(p) for p in self._render_both(tmp_path))
        assert np_peak > 1e-4, "il riferimento NumPy non ha prodotto suono"
        rapporto = sc_peak / np_peak
        assert 0.85 < rapporto < 1.15, (
            f"picchi troppo distanti: sc={sc_peak:.4f} numpy={np_peak:.4f} "
            f"(rapporto {rapporto:.2f}). Con la sonda a rampa decrescente un "
            f"rapporto intorno a 3 significa che i grani leggono dall'inizio "
            f"del file invece che da {READ_START_SEC}s."
        )

    def test_ampiezza_coerente_con_la_zona_letta(self, tmp_path):
        """Prova indipendente da NumPy: a READ_START_SEC la sonda vale
        1 - t/PROBE_DUR_SEC, e nessun grano puo' suonare piu' forte di cosi'
        (finestra e pan attenuano, non amplificano)."""
        sc_path, _ = self._render_both(tmp_path)
        massimo_teorico = 1.0 - READ_START_SEC / PROBE_DUR_SEC
        assert _peak(sc_path) < massimo_teorico * 1.05, (
            f"picco {_peak(sc_path):.4f} sopra l'ampiezza della sonda nella "
            f"zona letta ({massimo_teorico:.4f}): i grani stanno leggendo "
            f"altrove."
        )


# =============================================================================
# 5. PARITA' CON NUMPY
# =============================================================================

@pytest.mark.e2e
class TestParitaConNumpy:
    """Stesso YAML, stesso seed, due backend. La lista dei grani e' identica
    per costruzione: cio' che si confronta e' la resa.

    Non e' un confronto bit a bit -- restano differenze dichiarate (il DC
    blocker e il clamp sono post-processing del solo NumPy, l'interpolazione
    della tabella di finestra, il troncamento della rampa) -- ma la forma
    complessiva deve coincidere. Se qui i due divergono di molto, diverge il
    rendering, non la generazione.
    """

    def _render_both(self, tmp_path):
        sc_dir = tmp_path / "sc"
        np_dir = tmp_path / "np"
        sc_dir.mkdir()
        np_dir.mkdir()
        _make_build(sc_dir, renderer='supercollider')
        _make_build(np_dir, renderer='numpy')
        return (sc_dir / "output" / "e2e_sc_test.aif",
                np_dir / "output" / "e2e_sc_test.aif")

    def test_stessa_durata(self, tmp_path):
        import soundfile as sf

        sc_path, np_path = self._render_both(tmp_path)
        assert sf.info(str(sc_path)).duration == pytest.approx(
            sf.info(str(np_path)).duration, abs=0.15)

    def test_ampiezze_dello_stesso_ordine(self, tmp_path):
        sc_peak, np_peak = (_peak(p) for p in self._render_both(tmp_path))
        assert sc_peak > 1e-4 and np_peak > 1e-4
        assert 0.5 < sc_peak / np_peak < 2.0, (
            f"picchi troppo distanti: sc={sc_peak:.4f} numpy={np_peak:.4f}")

    def test_energia_distribuita_allo_stesso_modo_nel_tempo(self, tmp_path):
        """Confronto sulla forma, non sui campioni: l'RMS su finestre da
        100 ms deve seguire la stessa curva. E' la traduzione misurabile di
        'stessa densita', stessa traiettoria del pointer' -- e regge solo
        perche' il campione di prova ha un'ampiezza che varia nel tempo
        (vedi PROBE_SAMPLE): su un tono stazionario questa misura sarebbe
        cieca alla posizione di lettura."""
        import numpy as np
        import soundfile as sf

        sc_path, np_path = self._render_both(tmp_path)
        sc_audio, sr = sf.read(str(sc_path))
        np_audio, _ = sf.read(str(np_path))

        n = min(len(sc_audio), len(np_audio))
        block = sr // 10
        blocks = n // block

        def rms_curve(audio):
            mono = np.mean(audio[:blocks * block], axis=1)
            return np.sqrt(np.mean(mono.reshape(blocks, block) ** 2, axis=1))

        sc_rms, np_rms = rms_curve(sc_audio), rms_curve(np_audio)
        correlazione = np.corrcoef(sc_rms, np_rms)[0, 1]
        assert correlazione > 0.9, (
            f"le due rese non seguono la stessa curva (r={correlazione:.3f})")
