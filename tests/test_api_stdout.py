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

Entrambe le direzioni confrontano il token con l'inizio di una riga --
`riga.startswith(token)` a runtime, `prefisso_emesso.startswith(token)` da
sorgente. La relazione dev'essere la stessa nelle due, o l'elenco significa
due cose diverse a seconda di chi lo legge: con `token.strip() in
ast.unparse(node)` due voci su quindici non discriminavano piu' niente (vedi
il docstring di `_library_prints` e quello del test statico).

E c'e' una terza classe, che il censimento non copre ed e' per questo che il
censimento deve dichiarare il proprio perimetro: **stderr**. `TestStderr`
tiene fermo che i clip warning passano di la' e che l'intestazione di
`api.py` lo dica -- un elenco di stdout letto come inventario completo
rifarebbe l'errore della #189 un piano sotto.
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

# I print che `src/pge/` contiene ma che dall'API non si raggiungono. Non
# possono valere come prova che una voce del censimento sia ancora viva:
# senza questo elenco il token `[CACHE]` restava verde anche togliendo la
# riga per stream da tutti e tre i renderer -- cioe' proprio nello scenario
# #187/#188 che questo file dichiara di sorvegliare, sulla riga che PGE-ui
# parsa. Sono nominati per (modulo, funzione) e non per prefisso, perche' il
# prefisso e' identico a quello delle righe vive.
#
# L'elenco e' verificato, non trascritto: `test_le_esclusioni_sono_ancora_vere`
# chiede che ognuna esista ancora e che ogni sua chiamata in `src/pge/` stia
# dentro una funzione a sua volta esclusa -- il giorno che una diventa
# raggiungibile l'esclusione e' sbagliata e il test lo dice.
_UNREACHABLE = {
    # Generator.generate_score_files_per_stream: nessun chiamante in src/pge/
    ('generator.py', 'generate_score_files_per_stream'),
    # StreamCacheManager.get_dirty_stream_dicts: chiamata solo dalla
    # precedente, quindi irraggiungibile per la stessa ragione.
    ('stream_cache_manager.py', 'get_dirty_stream_dicts'),
}


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


def _emitted_prefix(node):
    """Il testo che il print emette PRIMA della prima interpolazione.

    E' la sola meta' della riga che si puo' leggere staticamente, ed e'
    quella che il censimento elenca: `[CACHE] {stream_id}: {status}` comincia
    per `[CACHE] `. Ritorna None per un print il cui primo argomento non e'
    una stringa (nessun prefisso da confrontare).
    """
    if not node.args:
        return None
    arg = node.args[0]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    if isinstance(arg, ast.JoinedStr):
        head = []
        for part in arg.values:
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                head.append(part.value)
            else:
                break
        return ''.join(head) if head else ''
    return None


def _iter_prints(path):
    """(funzione che lo contiene, nodo) per ogni `print(...)` del file."""
    tree = ast.parse(open(path, encoding='utf-8').read())
    trovati = []

    def walk(node, func):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func = node.name
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == 'print'):
            trovati.append((func, node))
        for child in ast.iter_child_nodes(node):
            walk(child, func)

    walk(tree, None)
    return trovati


def _library_prints(*, skip_unreachable=True):
    """Ogni `print(...)` di `src/pge/`, CLI esclusa, come record.

    Record: (modulo, funzione, prefisso emesso, sorgente). Il confronto col
    censimento e' sul **prefisso emesso**, non sul testo della chiamata: con
    `needle in ast.unparse(node)` il token `  - ` si riduceva a `-` dopo lo
    strip e veniva soddisfatto dalle frecce `->` dei print di
    `register_*_strategy`, cosi' che cancellare tutte e tre le righe di
    riepilogo dello ScoreWriter lasciava il test verde.
    """
    out = []
    for root, _dirs, files in os.walk(SRC_PGE):
        if '__pycache__' in root:
            continue
        for name in sorted(files):
            if not name.endswith('.py') or name in _NOT_LIBRARY:
                continue
            for func, node in _iter_prints(os.path.join(root, name)):
                if skip_unreachable and (name, func) in _UNREACHABLE:
                    continue
                out.append((name, func, _emitted_prefix(node),
                            ast.unparse(node)))
    return out


def _library_call_sites():
    """(modulo, funzione chiamante, nome chiamato) per ogni call di src/pge/.

    Il chiamante serve quanto il chiamato: `get_dirty_stream_dicts` ha un
    chiamante, ed e' `generate_score_files_per_stream` -- che a sua volta
    non ne ha. Senza il chiamante non si distingue "raggiungibile" da
    "raggiungibile solo da codice a sua volta irraggiungibile".
    """
    sites = []
    for root, _dirs, files in os.walk(SRC_PGE):
        if '__pycache__' in root:
            continue
        for name in sorted(files):
            if not name.endswith('.py'):
                continue
            path = os.path.join(root, name)
            tree = ast.parse(open(path, encoding='utf-8').read())

            def walk(node, func):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    func = node.name
                if isinstance(node, ast.Call):
                    fn = node.func
                    called = None
                    if isinstance(fn, ast.Name):
                        called = fn.id
                    elif isinstance(fn, ast.Attribute):
                        called = fn.attr
                    if called is not None:
                        sites.append((name, func, called))
                for child in ast.iter_child_nodes(node):
                    walk(child, func)

            walk(tree, None)
    return sites


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
        """La riga che la #189 ha trovato falsa non deve tornare.

        Falsa e' la forma **assoluta**: "nessun print". Qualificata --
        "nessun print nel proprio modulo", che e' la parola del piano e
        quella che `docs/explanation/library-vs-cli.md` e `tests/test_api.py`
        usano -- e' vera, e questo test non deve punirla: vietare la
        sottostringa e basta rendeva rosso il modo corretto di dirlo.
        """
        header = []
        for line in open(API_PATH, encoding='utf-8'):
            if not line.startswith('#'):
                break
            header.append(line)
        header = ''.join(header)
        for match in re.finditer(r'nessun print', header):
            coda = header[match.end():match.end() + 60]
            coda = ' '.join(coda.replace('#', ' ').split())
            assert coda.startswith('nel proprio modulo'), (
                "api.py torna a dichiarare 'nessun print' senza qualificarlo "
                "'nel proprio modulo': i componenti che orchestra stampano "
                "ancora (vedi gli altri test di questo file)")

    def test_le_esclusioni_sono_ancora_vere(self):
        """`_UNREACHABLE` e' verificato, non trascritto.

        Ogni esclusione deve (a) esistere ancora -- altrimenti descrive un
        print che non c'e' piu' e resta li' a nascondere il prossimo -- e
        (b) restare irraggiungibile, cioe' ogni sua chiamata in `src/pge/`
        deve stare dentro una funzione a sua volta esclusa. Il giorno che una
        diventa raggiungibile, l'esclusione e' sbagliata e va tolta.
        """
        vivi = {(mod, func)
                for mod, func, _pref, _src in _library_prints(
                    skip_unreachable=False)}
        esclusi = {func for _mod, func in _UNREACHABLE}
        siti = _library_call_sites()
        for mod, func in sorted(_UNREACHABLE):
            assert (mod, func) in vivi, (
                f"_UNREACHABLE elenca {mod}:{func}(), ma li' non c'e' piu' "
                f"nessun print(): togli la voce")
            fuori = [(m, chiamante) for m, chiamante, chiamato in siti
                     if chiamato == func and chiamante not in esclusi]
            assert not fuori, (
                f"_UNREACHABLE dichiara {mod}:{func}() irraggiungibile, ma "
                f"in src/pge/ la chiamano da {fuori}: le sue righe finiscono "
                f"su stdout e vanno censite, non escluse")

    def test_ogni_prefisso_elencato_esiste_ancora_come_print(self):
        """Direzione statica: l'elenco non sopravvive a chi lo svuota.

        Il confronto e' `prefisso_emesso.startswith(token)` -- la stessa
        relazione della direzione runtime (`riga.startswith(token)`), su cio'
        che il print emette davvero. Con `token.strip() in ast.unparse(node)`
        due voci su quindici non discriminavano nulla: `  - ` si riduceva a
        `-` e lo soddisfacevano le frecce `->` dei `register_*_strategy`
        (tolte tutte e tre le righe di riepilogo dello ScoreWriter, verde), e
        `[CACHE]` restava soddisfatto dalle righe irraggiungibili di
        `generator.py` / `stream_cache_manager.py` (tolta la riga per stream
        da tutti e tre i renderer, verde -- cioe' cieco proprio allo
        scenario qui sotto).

        Rosso previsto quando #187/#188 porteranno una di queste righe al
        logger. Non e' un falso allarme: e' la dichiarazione che va
        aggiornata insieme al comportamento.
        """
        prints = _library_prints()
        for token in _census_tokens():
            assert any(pref is not None and pref.startswith(token)
                       for _mod, _func, pref, _src in prints), (
                f"il censimento di api.py elenca {token!r}, ma in src/pge/ "
                f"nessun print() emette una riga che cominci cosi': "
                f"aggiorna l'elenco")


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
        # matplotlib.use() e non MPLBACKEND: la variabile d'ambiente la legge
        # matplotlib all'import, che l'importorskip qui sopra ha gia' fatto.
        import matplotlib
        matplotlib.use('Agg')
        pdf = str(probe['dir'] / 'census.pdf')
        _p, lines = _capture(lambda: api.export_score_pdf(
            gen, pdf, samples_dir=probe['samples']))

        blob = '\n'.join(lines)
        assert 'Esportazione PDF' in blob, lines
        assert '✓ PDF esportato' in blob, lines
        assert not _undocumented(lines, _census_tokens()), (
            f"righe non censite: {_undocumented(lines, _census_tokens())}")

    def test_le_funzioni_pure_restano_silenziose(self):
        """parameter_bounds/renderer_types non stampano: il censimento
        riguarda chi orchestra, non tutta l'API."""
        from pge import api
        for fn in (api.parameter_bounds, api.renderer_types):
            _r, lines = _capture(fn)
            assert lines == [], f"{fn.__name__} ha stampato: {lines}"

    def test_gli_export_non_partitura_restano_silenziosi(self, probe):
        """L'altra meta' della frase qui sopra, che prima era solo scritta.

        `export_score_pdf` fa parlare il visualizer; reaper, sv e grain json
        no, ed e' una differenza che il censimento afferma (li' compare solo
        il PDF). Un `print()` aggiunto a uno di questi tre passava sotto
        silenzio: il docstring li nominava, il ciclo no.
        """
        from pge import api
        gen, _ = _capture(
            lambda: api.load_generator(probe['yml'],
                                       samples_dir=probe['samples']))
        audio = str(probe['dir'] / 'probe.wav')
        casi = (
            ('export_reaper',
             lambda: api.export_reaper(gen, [audio],
                                       str(probe['dir'] / 'p.rpp'))),
            ('export_sv',
             lambda: api.export_sv(gen, audio,
                                   str(probe['dir'] / 'p.sv'))),
            ('export_grain_json',
             lambda: api.export_grain_json(gen, str(probe['dir']), 'p')),
        )
        for nome, fn in casi:
            _r, lines = _capture(fn)
            assert lines == [], f"{nome} ha stampato: {lines}"


# =============================================================================
# Lo stderr e' un canale a parte, e redirect_stdout non lo tocca
# =============================================================================

class TestStderr:
    """Il censimento e' di **stdout**, e dirlo per intero fa parte del punto.

    La #189 nasce da una dichiarazione che prometteva piu' silenzio di
    quanto ne consegnasse. Un censimento di stdout letto come inventario
    completo rifa' lo stesso errore un piano sotto: chi incorpora la libreria
    e mette `redirect_stdout` non ha silenziato niente di cio' che passa da
    qui.
    """

    def test_i_clip_warning_vanno_su_stderr_non_su_stdout(self, tmp_path):
        from pge.shared import logger as clip

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            clip.configure_clip_logger(log_dir=str(tmp_path / 'logs'))
            clip.log_clip_warning('s1', 'volume', 0.0, 5.0, 1.0, 0.0, 1.0)

        assert 'CLIP' in err.getvalue(), (
            f"il clip warning non e' su stderr: out={out.getvalue()!r} "
            f"err={err.getvalue()!r}")
        assert 'CLIP' not in out.getvalue(), (
            "il clip warning e' finito su stdout: se il canale e' cambiato, "
            "il censimento di api.py va aggiornato")

    def test_il_censimento_dichiara_di_essere_di_stdout(self):
        """Non basta che sia vero: deve dirlo, o si rilegge come completo."""
        header = []
        for line in open(API_PATH, encoding='utf-8'):
            if not line.startswith('#'):
                break
            header.append(line)
        header = ''.join(header)
        assert 'stderr' in header, (
            "l'intestazione di api.py censisce stdout senza dire che stderr "
            "esiste: redirect_stdout si legge allora come 'silenzio', e non "
            "lo e' (issue #189)")
