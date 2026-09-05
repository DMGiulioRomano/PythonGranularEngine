"""Il sample sintetico deve arrivare a chi lo legge (issue #243).

`utils/bench_cost.py` sceglie una directory di sample e la passa a due
consumatori: il `Generator` (che risolve il sample in generazione) e il
renderer (che lo legge in overlap-add). La classe di bug che la #243 ha
prodotto era invisibile a review e CI: `cli._build_renderer(tipo, gen, **kwargs)`
pescava i kwargs con `.get()`, quindi un nome sbagliato — `ssdir=`, che vale
solo per Csound — non era un TypeError ma un no-op silenzioso, e la directory
ricadeva sul default storico `./refs/`. La #252 ha chiuso anche quella porta
(firma esplicita); qui resta il comportamento osservabile, che non dipende da
quale delle due la difende.

Qui si asserisce il comportamento osservabile: il sample viene risolto nella
directory giusta, sia negli sweep (che non passano nessun argomento: e' il
percorso della issue) sia quando la directory e' esplicita. Piu' la separazione
fra le due directory in gioco, che un unico globale aveva confuso: quella degli
sweep (la tmpdir del seno sintetico) e quella del caso di riferimento (uno YAML
reale, che cita il proprio sample e lo cerca in `refs/`).
"""
from __future__ import annotations

import glob
import os
import subprocess
import sys
import tempfile

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def bench():
    sys.path.insert(1, os.path.join(REPO_ROOT, "utils"))
    import bench_cost

    return bench_cost


@pytest.fixture
def clone_pulito(bench, monkeypatch, tmp_path):
    """Lo stato della issue: `refs/` senza `voice.wav`, sweep sul seno.

    `refs/` viene sostituita da una directory vuota invece di leggere quella
    vera: cosi' il test dice la stessa cosa in CI (dove `voice.wav` non c'e'
    mai) e sulla macchina di chi quel file ce l'ha. Senza, l'asserzione
    diventerebbe una disgiunzione sui due stati dell'ambiente, cioe' qualcosa
    che non puo' fallire in modo informativo.
    """
    vuota = tmp_path / "refs_vuota"
    vuota.mkdir()
    lavoro = tmp_path / "out"
    lavoro.mkdir()
    monkeypatch.setattr(bench, "REFS", str(vuota))
    monkeypatch.setattr(bench, "_OUT", str(lavoro))
    monkeypatch.setattr(bench, "_SWEEP", None)
    return bench


def _scrivi_sample_e_yaml(bench, tmp_path):
    """Un seno in una directory che non e' ne' `refs/` ne' quella degli sweep."""
    import make_test_samples

    samples_dir = tmp_path / "samples"
    samples_dir.mkdir()
    make_test_samples.genera(
        str(samples_dir / "solo_qui.wav"), freq=220.0, dur=1.0, sr=bench.SR
    )
    yml = tmp_path / "bench.yml"
    yml.write_text(
        bench.YAML_TEMPLATE.format(dur=0.5, den=20, sample="solo_qui.wav")
    )
    return str(samples_dir), str(yml)


def test_gli_sweep_risolvono_il_sample_su_un_clone_pulito(clone_pulito):
    """Il sintomo della #243: `once()` non passa `samples_dir`, e deve girare.

    E' il ramo che gli sweep usano davvero. Rimettere `REFS` come default di
    `_load`/`_render` — la mutazione piu' naturale — fa morire questo test in
    `SampleNotFoundError`, che e' letteralmente la issue: su un clone pulito lo
    script non arrivava a misurare niente.
    """
    bench = clone_pulito
    nome, samples_dir = bench.sweep_sample()
    assert (nome, samples_dir) == ("bench_sample.wav", bench.out_dir())

    yml = os.path.join(bench.out_dir(), "sweep.yml")
    with open(yml, "w") as handle:
        handle.write(bench.YAML_TEMPLATE.format(dur=0.5, den=20, sample=nome))

    generator = bench._load(yml)
    assert bench._render(generator) > 0


def test_con_voice_wav_in_refs_gli_sweep_usano_quello(bench, monkeypatch, tmp_path):
    """L'altro ramo: con `refs/voice.wav` presente non si genera niente."""
    import make_test_samples

    refs = tmp_path / "refs"
    refs.mkdir()
    make_test_samples.genera(str(refs / "voice.wav"), freq=220.0, dur=1.0, sr=bench.SR)
    monkeypatch.setattr(bench, "REFS", str(refs))
    monkeypatch.setattr(bench, "_OUT", None)
    monkeypatch.setattr(bench, "_SWEEP", None)

    assert bench.sweep_sample() == ("voice.wav", str(refs))
    assert bench._OUT is None  # nessuna directory di lavoro creata per nulla


def test_il_render_risolve_il_sample_nella_samples_dir(bench, monkeypatch, tmp_path):
    """Il test portante: con `ssdir=` al posto di `samples_dir=` qui si muore.

    Il sample esiste solo nella directory passata, quindi il fallback su
    `./refs/` non puo' mascherare nulla. `_load` copre la generazione,
    `_render` il rendering: sono i due difetti indipendenti della #243, e
    correggerne uno solo sposta l'errore invece di toglierlo.
    """
    monkeypatch.setattr(bench, "_OUT", str(tmp_path))
    samples_dir, yml = _scrivi_sample_e_yaml(bench, tmp_path)

    generator = bench._load(yml, samples_dir=samples_dir)
    assert bench._render(generator, samples_dir=samples_dir) > 0


def test_il_caso_di_riferimento_non_eredita_la_dir_degli_sweep(bench, monkeypatch):
    """`once_yaml` legge da `refs/`, non dalla tmpdir del seno sintetico.

    Quando `refs/voice.wav` manca, la directory degli sweep e' una tmpdir che
    contiene *solo* `bench_sample.wav`: uno YAML reale che cita il proprio
    sample non ci si trova. Lo stato non e' ipotetico — `make test-samples`
    scrive `refs/pino.wav` e non `voice.wav`, ed e' prerequisito di
    `make e2e-tests`.

    `samples_dir=None` esplicito vale come l'assenza dell'argomento: in
    `_load`/`_render` quella sentinella significa "la directory degli sweep",
    e inoltrarla tal quale rimetterebbe il caso di riferimento proprio li'.
    """
    visti = []

    class _FakeStream:
        onset, duration, voices = 0.0, 1.0, [[]]

    class _FakeGenerator:
        streams = [_FakeStream()]

    monkeypatch.setattr(
        bench, "_load",
        lambda path, samples_dir=None: visti.append(("load", samples_dir))
        or _FakeGenerator(),
    )
    monkeypatch.setattr(
        bench, "_render",
        lambda gen, samples_dir=None: visti.append(("render", samples_dir)) or 0.0,
    )

    bench.once_yaml("/non/letto.yml")
    bench.once_yaml("/non/letto.yml", samples_dir=None)

    assert visti == [("load", bench.REFS), ("render", bench.REFS)] * 2
    assert bench.REFS == os.path.join(REPO_ROOT, "refs")


def test_run_yaml_inoltra_la_samples_dir(bench, monkeypatch):
    """La manopola arriva fino in fondo, non si ferma a `once_yaml`."""
    visti = []
    monkeypatch.setattr(
        bench, "once_yaml",
        lambda path, samples_dir=None: visti.append(samples_dir)
        or (1.0, 10, 2.0, 0.1, 0.2, 0.7),
    )

    riga = bench.run_yaml("/non/letto.yml", samples_dir="/altrove")

    assert visti == ["/altrove"] * bench.REPS
    assert riga["samples_dir"] == "/altrove"


def test_il_renderer_riceve_samples_dir_e_non_ssdir(bench, monkeypatch):
    """Il nome del kwarg, per esteso: `.get()` non protestava su quello sbagliato."""
    catturati = {}

    class _FakeEngine:
        def __init__(self, renderer):
            pass

        def render(self, **kwargs):
            return None

    monkeypatch.setattr(
        bench.api, "build_renderer",
        lambda tipo, gen, **kwargs: catturati.update(tipo=tipo, **kwargs),
    )
    monkeypatch.setattr(bench, "RenderingEngine", _FakeEngine)
    monkeypatch.setattr(bench, "_OUT", "/non/scritto")

    class _FakeGenerator:
        streams = []

    bench._render(_FakeGenerator(), samples_dir="/dev/null/x")

    assert catturati["samples_dir"] == "/dev/null/x"
    assert "ssdir" not in catturati
    assert "sfdir" not in catturati


def test_lapi_rifiuta_il_kwarg_sbagliato(bench):
    """Il fix strutturale: sull'API pubblica `ssdir=` e' un TypeError.

    `cli._build_renderer` lo avrebbe ingoiato con `.get()` senza dire niente —
    e' cosi' che la #243 e' potuta nascere. Passando da `api.build_renderer` la
    stessa svista non e' piu' scrivibile in silenzio; dalla #252 non lo e' piu'
    nemmeno dall'altra parte, ma il chiamante giusto resta questo.
    """
    with pytest.raises(TypeError):
        bench.api.build_renderer("numpy", object(), ssdir="/x")


def test_il_sample_del_caso_di_riferimento_e_verificato_prima_degli_sweep(
    bench, monkeypatch, tmp_path
):
    """Fail-fast: `configs/PGE_cim.yml` cita `voice.wav`, cioe' il file mancante.

    Su un clone pulito il caso documentato (`make bench YAML=...`) muore sul
    proprio sample. Se muore dopo i tre sweep si porta via un minuto e mezzo di
    misure, perche' il `json.dump` viene dopo. Qui si verifica sia che
    `check_ref_sample` sollevi, sia che `main()` lo faccia prima di far partire
    gli sweep.
    """
    monkeypatch.setattr(bench, "_SWEEP", None)
    yml = tmp_path / "ref.yml"
    yml.write_text(bench.YAML_TEMPLATE.format(dur=0.5, den=20, sample="manca.wav"))

    with pytest.raises(SystemExit) as errore:
        bench.check_ref_sample(str(yml), samples_dir=str(tmp_path))
    assert "manca.wav" in str(errore.value)

    # Senza argomento la verifica guarda in `refs/`, non nella directory degli
    # sweep: e' la stessa sentinella invertita che la #243 ha prodotto in
    # `once_yaml`, e qui era stata riprodotta pari pari.
    with pytest.raises(SystemExit) as errore:
        bench.check_ref_sample(str(yml))
    assert bench.REFS in str(errore.value)
    assert bench._SWEEP is None  # il seno degli sweep non e' stato nemmeno scritto

    def _sweep_vietato(*args, **kwargs):
        raise AssertionError("gli sweep sono partiti prima della verifica")

    monkeypatch.setattr(bench, "run", _sweep_vietato)
    monkeypatch.setattr(sys, "argv", ["bench_cost.py", str(yml), str(tmp_path)])
    with pytest.raises(SystemExit):
        bench.main()


def test_importare_il_modulo_non_tocca_il_filesystem():
    """Un import non deve creare la tmpdir ne' scriverci dentro il seno.

    `import bench_cost` da un test faceva `mkdtemp` + `ensure_sample()`: ogni
    `make tests` lasciava una `/tmp/pge_bench_*` orfana e, dove `voice.wav`
    manca (la CI), ci scriveva dentro un wav da ~288 KB. Lo stato ora e' pigro,
    e questo test lo verifica dove si vede: in un processo nuovo.
    """
    codice = (
        "import sys; sys.path.insert(1, %r); import bench_cost as b;"
        "print(b._OUT, b._SWEEP)" % os.path.join(REPO_ROOT, "utils")
    )
    modello = os.path.join(tempfile.gettempdir(), "pge_bench_*")
    prima = set(glob.glob(modello))

    esito = subprocess.run(
        [sys.executable, "-c", codice],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )

    assert esito.returncode == 0, esito.stderr
    assert esito.stdout.strip() == "None None"
    assert set(glob.glob(modello)) == prima
