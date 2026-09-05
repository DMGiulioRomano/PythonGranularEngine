# tests/test_api_stdout.py
"""
Il contratto stdout di `pge.api`, verificato su output vero (issue #189).

L'intestazione di `api.py` dichiarava "nessun print". La dichiarazione era
falsa, e i test che sembravano difenderla non potevano accorgersene:
`tests/test_api.py` monta `Generator`, `RenderingEngine` e `ScoreVisualizer`
come MagicMock, quindi il `capsys` vuoto dei suoi `test_no_print` misura il
silenzio dei mock, non quello della libreria. Quei test restano veri su cio'
che dicono davvero -- nessuna funzione di `api.py` contiene un `print()` --
e questo file copre l'altra meta': cosa vede su stdout chi chiama l'API con
i componenti veri, che e' la domanda di chi la incorpora.

Il censimento chiude in due direzioni, e servono entrambe:

- **runtime** -- ogni riga che un render vero scrive su stdout deve essere
  una di quelle che il censimento in `api.py` elenca. Un `print()` nuovo che
  arriva fino all'API senza passare dalla dichiarazione e' rosso.
- **statico** -- ogni prefisso elencato deve esistere ancora come `print()`
  dentro `src/pge/`. Quando #187/#188 porteranno quelle righe al logger,
  l'elenco diventera' stale: qui diventa rosso, invece di restare a
  descrivere un comportamento che non c'e' piu'.

La prima direzione da sola lascerebbe crescere l'elenco all'infinito; la
seconda da sola non vedrebbe mai una riga nuova.
"""

import ast
import io
import os
import re
import contextlib

import pytest

SRC_PGE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'src', 'pge')
)
API_PATH = os.path.join(SRC_PGE, 'api.py')

# Delimitatori del blocco censimento nell'intestazione di api.py. Sono la
# ragione per cui l'estrazione non deve indovinare dove finisce la prosa.
_BEGIN = '--- righe su stdout'
_END = '--- fine censimento'

# La CLI e' l'altro lato del contratto: i suoi print sono policy sua e non
# c'entrano con cosa vede chi importa la libreria.
_NOT_LIBRARY = {'cli.py'}


def _census_tokens():
    """I prefissi backtickati elencati nel censimento di `api.py`."""
    lines = open(API_PATH, encoding='utf-8').read().splitlines()
    start = end = None
    for i, line in enumerate(lines):
        if _BEGIN in line:
            start = i
        elif _END in line and start is not None:
            end = i
            break
    assert start is not None and end is not None, (
        f"blocco censimento non trovato in {API_PATH}: servono le righe "
        f"'{_BEGIN}' e '{_END}'"
    )
    # Una voce del censimento e' una riga che APRE con il prefisso
    # backtickato; i backtick che compaiono piu' avanti sono prosa (un nome
    # di parametro, una chiave YAML) e non righe di stdout.
    tokens = []
    for line in lines[start:end]:
        body = line.lstrip('#').strip()
        if not body.startswith('`'):
            continue
        match = re.match(r'`([^`]+)`', body)
        if match:
            tokens.append(match.group(1))
    return tokens


def _library_print_sources():
    """Il testo di ogni `print(...)` di `src/pge/`, CLI esclusa."""
    out = []
    for root, _dirs, files in os.walk(SRC_PGE):
        if '__pycache__' in root:
            continue
        for name in files:
            if not name.endswith('.py') or name in _NOT_LIBRARY:
                continue
            path = os.path.join(root, name)
            tree = ast.parse(open(path, encoding='utf-8').read())
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name)
                        and node.func.id == 'print'):
                    out.append((path, ast.unparse(node)))
    return out


def _write_sample(tmp_path, name='probe.wav', dur=1.0, sr=48000):
    """Un wav vero in tmp_path: `refs/` in un checkout pulito e' vuota."""
    import numpy as np
    import soundfile as sf
    sf.write(str(tmp_path / name),
             np.zeros(int(dur * sr), dtype='float32'), sr)
    return name


_YAML = """\
composition:
  title: "stdout census"

streams:
  - stream_id: "s1"
    onset: 0.0
    duration: 0.3
    sample: "probe.wav"
  - stream_id: "s2"
    onset: 0.3
    duration: 0.3
    sample: "probe.wav"
    mute: true
"""


@pytest.fixture
def probe(tmp_path):
    """YAML + sample veri; niente `seed:`, cosi' la riga [SEED] si vede."""
    _write_sample(tmp_path)
    yml = tmp_path / 'census.yml'
    yml.write_text(_YAML)
    return {'yml': str(yml), 'samples': str(tmp_path), 'dir': tmp_path}


def _capture(fn):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = fn()
    return result, [ln for ln in buf.getvalue().splitlines() if ln.strip()]


def _undocumented(lines, tokens):
    return [ln for ln in lines
            if not any(ln.startswith(t) for t in tokens)]


# =============================================================================
# Il censimento esiste, ed e' fatto di prefissi veri
# =============================================================================

class TestCensimento:

    def test_il_blocco_esiste_e_non_e_vuoto(self):
        assert _census_tokens(), (
            "il censimento di api.py non elenca nessun prefisso: una "
            "libreria che dichiara cosa stampa deve dire cosa")

    def test_api_non_dichiara_piu_silenzio_assoluto(self):
        """La riga che la #189 ha trovato falsa non deve tornare."""
        header = []
        for line in open(API_PATH, encoding='utf-8'):
            if not line.startswith('#'):
                break
            header.append(line)
        header = ''.join(header)
        assert 'nessun print' not in header, (
            "api.py torna a dichiarare 'nessun print': i componenti che "
            "orchestra stampano ancora (vedi gli altri test di questo file)")

    def test_ogni_prefisso_elencato_esiste_ancora_come_print(self):
        """Direzione statica: l'elenco non sopravvive a chi lo svuota.

        Rosso previsto quando #187/#188 porteranno una di queste righe al
        logger. Non e' un falso allarme: e' la dichiarazione che va
        aggiornata insieme al comportamento.
        """
        sources = _library_print_sources()
        for token in _census_tokens():
            needle = token.strip()
            assert any(needle in text for _path, text in sources), (
                f"il censimento di api.py elenca {token!r}, ma in src/pge/ "
                f"nessun print() lo emette piu': aggiorna l'elenco")


# =============================================================================
# Direzione runtime: cosa stampa davvero l'API con i componenti veri
# =============================================================================

class TestStdoutReale:

    def test_load_generator_non_e_silenzioso(self, probe):
        """Il cuore della #189: la libreria non tace, e questo lo prova
        senza mock in mezzo."""
        from pge import api
        _gen, lines = _capture(
            lambda: api.load_generator(probe['yml'],
                                       samples_dir=probe['samples']))
        assert lines, (
            "load_generator non ha stampato niente: se e' diventato vero, "
            "la dichiarazione in api.py va riscritta di conseguenza")

    def test_ogni_riga_di_load_generator_e_censita(self, probe):
        from pge import api
        _gen, lines = _capture(
            lambda: api.load_generator(probe['yml'],
                                       samples_dir=probe['samples']))
        assert not _undocumented(lines, _census_tokens()), (
            f"righe su stdout che il censimento di api.py non elenca: "
            f"{_undocumented(lines, _census_tokens())}")

    def test_le_righe_del_generator_ci_sono_tutte(self, probe):
        """Il test precedente da solo passerebbe anche su stdout vuoto."""
        from pge import api
        _gen, lines = _capture(
            lambda: api.load_generator(probe['yml'],
                                       samples_dir=probe['samples']))
        blob = '\n'.join(lines)
        for atteso in ('[SEED]', '🔇', 'Creazione di', '→ Stream'):
            assert atteso in blob, f"manca la riga {atteso!r}: {lines}"

    def test_render_stampa_lo_stato_della_cache(self, probe):
        """`[CACHE] <id>: DIRTY|clean`, una riga per stream, dal renderer."""
        from pge import api
        gen, _ = _capture(
            lambda: api.load_generator(probe['yml'],
                                       samples_dir=probe['samples']))
        manifest = str(probe['dir'] / 'manifest.json')
        out = str(probe['dir'] / 'stem.wav')
        _res, lines = _capture(lambda: api.render(
            gen, out, renderer='numpy', per_stream=True,
            samples_dir=probe['samples'], cache_manifest_path=manifest))

        assert any(ln.startswith('[CACHE]') for ln in lines), lines
        assert not _undocumented(lines, _census_tokens()), (
            f"righe non censite: {_undocumented(lines, _census_tokens())}")

    def test_senza_manifest_non_c_e_riga_di_cache(self, probe):
        """`[CACHE]` e' condizionata a `cache_manifest_path`, e il
        censimento lo dice: senza manifest quella riga non esiste."""
        from pge import api
        gen, _ = _capture(
            lambda: api.load_generator(probe['yml'],
                                       samples_dir=probe['samples']))
        out = str(probe['dir'] / 'mix.wav')
        _res, lines = _capture(lambda: api.render(
            gen, out, renderer='numpy', samples_dir=probe['samples']))

        assert not [ln for ln in lines if ln.startswith('[CACHE]')], lines
        assert not _undocumented(lines, _census_tokens()), (
            f"righe non censite: {_undocumented(lines, _census_tokens())}")

    def test_export_score_pdf_stampa_la_partitura(self, probe, monkeypatch):
        """ScoreVisualizer e' la terza fonte, e la piu' loquace."""
        pytest.importorskip('matplotlib')
        from pge import api
        gen, _ = _capture(
            lambda: api.load_generator(probe['yml'],
                                       samples_dir=probe['samples']))
        # chdir: il clip logger scrive ./logs alla prima inizializzazione,
        # e un test non sporca la root del repo.
        monkeypatch.chdir(probe['dir'])
        monkeypatch.setenv('MPLBACKEND', 'Agg')
        pdf = str(probe['dir'] / 'census.pdf')
        _p, lines = _capture(lambda: api.export_score_pdf(
            gen, pdf, samples_dir=probe['samples']))

        blob = '\n'.join(lines)
        assert 'Esportazione PDF' in blob, lines
        assert '✓ PDF esportato' in blob, lines
        assert not _undocumented(lines, _census_tokens()), (
            f"righe non censite: {_undocumented(lines, _census_tokens())}")

    def test_le_funzioni_pure_restano_silenziose(self, probe):
        """parameter_bounds/renderer_types e gli export non-partitura non
        stampano: il censimento riguarda chi orchestra, non tutta l'API."""
        from pge import api
        for fn in (api.parameter_bounds, api.renderer_types):
            _r, lines = _capture(fn)
            assert lines == [], f"{fn.__name__} ha stampato: {lines}"
