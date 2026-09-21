# =============================================================================
# tests/test_suite_contract.py
# =============================================================================
"""
Il nome di un file di test è una promessa (issue #274).

`tests/<area>/test_<modulo>.py` dice di sorvegliare `src/pge/<area>/<modulo>.py`.
Questa suite pretende che la promessa sia mantenuta, e lo chiede in due
direzioni opposte:

- il file **importa** il modulo che nomina;
- il file **non ne riscrive** le classi e le funzioni pubbliche a livello di
  modulo.

Le due metà servono entrambe perché una sola è verde sul difetto dell'altra.
`tests/parameters/test_parameter.py` importa davvero `pge.parameters.parameter`
— in fondo al file, dentro `_import_real_parameter()`, per i 9 test di
`TestResolveParam` — e accanto ridefinisce `class Parameter`: sulla prima metà
passa. `tests/parameters/test_parser.py` non importa niente e riscrive
`GranularParser`: passerebbe una guardia che guardasse solo i nomi ridefiniti
se un giorno rinominasse la propria copia.

## Perché

La #274 ha misurato che tre file della suite non eseguono una riga del modulo
che nominano. Non è un buco di copertura — quei moduli sono coperti dal
*resto* della suite, al 97%, al 95% e all'85% — ma un'esca: chi modifica
`parameter.py` apre `test_parameter.py`, legge 72 test sul comportamento di
`Parameter`, e sta leggendo il comportamento di un'altra classe che si chiama
allo stesso modo. Nella PR #273 è successo per tre volte di fila: i due file
non hanno potuto né confermare né smentire, e sono rimasti verdi.

Il difetto è muto per costruzione: una riscrittura non fallisce mai, e il
giorno in cui il modulo vero cambia comportamento la copia resta coerente con
sé stessa. Questa guardia è il rumore che gli mancava. Trova i tre di oggi —
dichiarati qui sotto — e il quarto il giorno in cui nasce, invece che alla
prossima review.

## Che cosa la guardia non dice

Che il modulo sia *testato*. Importarlo è il minimo osservabile da un AST, non
il presidio: `test_parameter.py` importa e resta, per 63 test su 72, la
riscrittura che è. La guardia dice soltanto che il file omonimo tocca il
modulo omonimo, e la `SIMULAZIONI_DICHIARATE` dice chi non lo fa e perché —
che è il valore vero di questa suite: il debito smette di essere invisibile e
diventa una riga che qualcuno deve cancellare.

Limite dichiarato: la corrispondenza è esatta sul nome. `tests/test_cli_*.py`
non nomina nessun modulo (`pge/cli_contract.py` non esiste) e non entra fra le
coppie; `tests/parameters/test_parser_errors.py` nemmeno. Sorvegliano
`pge.cli` e `pge.parameters.parser` per contenuto, non per nome, e non è a
questa guardia che tocca dirlo.

## Riferimenti

- #274 — la misura da cui questa suite nasce
- #272 / PR #273 — la modifica che ha fatto emergere il buco
- `tests/shared/test_stdout_contract.py` — il precedente di una guardia letta
  dai sorgenti invece che scritta a mano
"""
import ast
import os

import pytest

TESTS_DIR = os.path.abspath(os.path.dirname(__file__))
SRC_PGE = os.path.abspath(os.path.join(TESTS_DIR, '..', 'src', 'pge'))

# Le simulazioni: file che nominano un modulo e non lo eseguono. La lista è
# il punto di questa suite — dice quali test sono una riscrittura e perché,
# invece di lasciarlo scoprire a chi modifica il modulo.
#
# Nessuna delle tre è una simulazione *voluta*: sono il debito che la #274
# registra. Si tolgono da qui riscrivendole contro produzione (opzione 4 della
# issue), e il momento giusto è quando qualcuno tocca quei moduli per un'altra
# ragione.
SIMULAZIONI_DICHIARATE = {
    os.path.join('parameters', 'test_parameter.py'): (
        "Riscrive Parameter, ParameterBounds, Envelope e le factory di gate, "
        "variation e distribution. Solo TestResolveParam (9 test su 72) "
        "importa il modulo vero, per resolve_param e StrategyParam. Il suo "
        "_clamp è la grafia che la #272 ha tolto da produzione, e il suo "
        "ParameterBounds non sa esprimere un tetto assente, quindi non può "
        "nemmeno accorgersene. Issue #274."
    ),
    os.path.join('parameters', 'test_parser.py'): (
        "Riscrive GranularParser — _validate_and_clip compreso, cioè proprio "
        "la macchina strict/permissive che la PR #273 ha toccato — e accanto "
        "Envelope, ParameterBounds, Parameter, StreamConfig e due funzioni di "
        "supporto. Non importa `pge.parameters.parser` in nessun punto. "
        "Issue #274."
    ),
    os.path.join('shared', 'test_probability_gate.py'): (
        "Riscrive i cinque gate (ProbabilityGate, NeverGate, AlwaysGate, "
        "RandomGate, EnvelopeGate) e non importa `pge.shared.probability_gate`. "
        "Trovato da questa guardia, non dalla #274, che ne censiva due: è il "
        "primo effetto di averla scritta."
    ),
}


# =============================================================================
# SCOPERTA — le coppie (file di test, modulo che nomina)
# =============================================================================

def _coppie():
    """`(relpath sotto tests/, modulo puntato, path del sorgente)`.

    Solo dove il modulo nominato esiste davvero: un `test_<x>.py` che non
    corrisponde a nessun `<x>.py` non promette niente e non è affare di
    questa suite.
    """
    trovate = []
    for radice, cartelle, files in os.walk(TESTS_DIR):
        cartelle[:] = [c for c in cartelle if c != '__pycache__']
        area = os.path.relpath(radice, TESTS_DIR)
        area = '' if area == '.' else area
        # Solo il primo livello: `tests/<area>/` e la radice. Più in fondo
        # non c'è una cartella che corrisponda a un package di `pge`.
        if os.sep in area:
            continue
        for nome in sorted(files):
            if not (nome.startswith('test_') and nome.endswith('.py')):
                continue
            modulo = nome[len('test_'):-len('.py')]
            sorgente = os.path.join(SRC_PGE, area, modulo + '.py')
            if not os.path.isfile(sorgente):
                continue
            puntato = '.'.join(x for x in ('pge', area, modulo) if x)
            trovate.append((os.path.join(area, nome), puntato, sorgente))
    return sorted(trovate)


def _sorvegliate():
    """Le coppie su cui le due guardie parlano: tutte meno le dichiarate."""
    return [(rel, mod) for rel, mod, _ in _coppie()
            if rel not in SIMULAZIONI_DICHIARATE]


def _albero(path):
    with open(path, encoding='utf-8') as f:
        return ast.parse(f.read())


# =============================================================================
# I DUE CRITERI
# =============================================================================

def _importa(tree, puntato):
    """Il sorgente nomina `puntato` come bersaglio di un import.

    Quattro grafie, perché la suite le usa tutte e contarne tre lascerebbe
    verde un file che usa la quarta:

        import pge.a.m [as x]
        from pge.a.m import X
        from pge.a import m [as x]
        importlib.import_module('pge.a.m')

    L'ultima non è un vezzo: è l'unica con cui `test_parameter.py` tocca
    produzione, e leggere solo gli `import` la darebbe per assente.

    Il confronto è esatto oppure sul prefisso **seguito da un punto**, e quel
    punto è il criterio: `pge.parameters.parameter_definitions` comincia per
    `pge.parameters.parameter` e non è quel modulo. Senza il punto
    `test_parameter.py` passerebbe questa metà per via di un import che
    riguarda un altro file.

    Si cammina tutto l'albero, non solo `tree.body`: un import dentro una
    funzione o dentro una fixture è un import.
    """
    def combacia(nome):
        return nome == puntato or nome.startswith(puntato + '.')

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(combacia(a.name) for a in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.level or not node.module:
                continue
            if combacia(node.module):
                return True
            # `from pge.a import m`: il modulo è nel nome importato.
            if any(combacia(node.module + '.' + a.name) for a in node.names):
                return True
        elif isinstance(node, ast.Call):
            func = node.func
            nome = func.attr if isinstance(func, ast.Attribute) else (
                func.id if isinstance(func, ast.Name) else None)
            if nome != 'import_module' or not node.args:
                continue
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                if combacia(arg.value):
                    return True
    return False


def _nomi_di_modulo(tree):
    """Classi e funzioni definite **a livello di modulo**.

    Solo il primo livello: una classe finta dentro una fixture è un dettaglio
    di un test, una classe finta a livello di modulo è ciò che il resto del
    file usa al posto del modulo vero — ed è la forma che hanno tutte e tre
    le riscritture censite.
    """
    return {n.name for n in tree.body
            if isinstance(n, (ast.ClassDef, ast.FunctionDef,
                              ast.AsyncFunctionDef))}


def _nomi_pubblici(path):
    """Classi e funzioni pubbliche che il modulo espone al primo livello.

    Le costanti restano fuori di proposito: un test che dichiara un
    `DENSITY_BOUNDS` accanto a quello del modulo sta scrivendo una fixture,
    non una riscrittura, e accusarlo renderebbe la guardia rumorosa proprio
    dove non ha niente da dire.
    """
    return {n.name for n in _albero(path).body
            if isinstance(n, (ast.ClassDef, ast.FunctionDef,
                              ast.AsyncFunctionDef))
            and not n.name.startswith('_')}


def _riscritture(rel_test, sorgente):
    """I nomi pubblici del modulo che il file di test ridefinisce."""
    tree = _albero(os.path.join(TESTS_DIR, rel_test))
    return _nomi_di_modulo(tree) & _nomi_pubblici(sorgente)


# =============================================================================
# 1. LE DUE GUARDIE
# =============================================================================

@pytest.mark.parametrize('rel_test,puntato', _sorvegliate())
def test_il_file_omonimo_importa_il_modulo_che_nomina(rel_test, puntato):
    """Chi porta il nome di un modulo lo esegue.

    Un file che non lo importa può essere verde per sempre mentre il modulo
    cambia sotto: è il caso che la #274 ha misurato su `test_parser.py`, 51
    test e zero righe di produzione.
    """
    tree = _albero(os.path.join(TESTS_DIR, rel_test))

    assert _importa(tree, puntato), (
        f"tests/{rel_test} non importa `{puntato}`, cioè il modulo che il suo "
        "nome promette di sorvegliare. Se è una simulazione voluta, "
        "dichiarala in SIMULAZIONI_DICHIARATE con il motivo; altrimenti "
        "scrivi i test contro produzione. Vedi issue #274."
    )


@pytest.mark.parametrize('rel_test,puntato', _sorvegliate())
def test_il_file_omonimo_non_riscrive_il_modulo_che_nomina(rel_test, puntato):
    """Importarlo non basta: accanto non può starci una copia.

    Una classe di produzione ridefinita a livello di modulo prende il posto
    di quella vera per tutto il file — anche per i test che il modulo vero
    l'avevano importata. È la forma esatta di `test_parameter.py`, che
    importa `pge.parameters.parameter` e poi fa girare 63 test su una
    `class Parameter` propria.
    """
    sorgente = os.path.join(SRC_PGE, *puntato.split('.')[1:]) + '.py'
    doppioni = _riscritture(rel_test, sorgente)

    assert not doppioni, (
        f"tests/{rel_test} ridefinisce a livello di modulo "
        f"{sorted(doppioni)}, che `{puntato}` espone. Chi legge il file crede "
        "di leggere il comportamento del modulo e legge quello della copia. "
        "Se la simulazione è voluta, dichiarala in SIMULAZIONI_DICHIARATE. "
        "Vedi issue #274."
    )


# =============================================================================
# 2. LA LISTA NON INVECCHIA
# =============================================================================

def test_ogni_simulazione_dichiarata_e_ancora_una_simulazione():
    """Un'eccezione che ha smesso di violare va tolta, non lasciata lì.

    È la metà che tiene in piedi la lista: senza, una riscrittura convertita
    contro produzione lascerebbe il suo file dichiarato per sempre, e la
    dichiarazione — che è il documento che questa suite produce — comincerebbe
    a dire il falso. Vale anche per un file rinominato o cancellato.

    Fallisce anche quando a rompersi è la scoperta: se `_coppie()` smette di
    trovare le coppie, le tre dichiarate spariscono da lì e questo test lo
    dice. È il canarino delle due guardie qui sopra, che a scoperta vuota
    sarebbero verdi senza guardare niente.
    """
    trovate = {rel: (mod, src) for rel, mod, src in _coppie()}

    for rel, motivo in sorted(SIMULAZIONI_DICHIARATE.items()):
        assert motivo.strip(), f"{rel}: dichiarata senza motivo"
        assert rel in trovate, (
            f"SIMULAZIONI_DICHIARATE dichiara tests/{rel}, che la scoperta "
            "non trova: o il file non esiste più, o non nomina più un modulo "
            "di `pge`, o `_coppie()` si è rotta. Toglilo dalla lista, "
            "oppure aggiusta la scoperta."
        )
        puntato, sorgente = trovate[rel]
        tree = _albero(os.path.join(TESTS_DIR, rel))
        viola = (not _importa(tree, puntato)
                 or bool(_riscritture(rel, sorgente)))
        assert viola, (
            f"tests/{rel} importa `{puntato}` e non ne riscrive più i nomi "
            "pubblici: non è più una simulazione. Toglila da "
            "SIMULAZIONI_DICHIARATE — da qui in poi la sorvegliano le due "
            "guardie."
        )


def test_la_scoperta_vede_la_suite():
    """Un pavimento sul numero di coppie, non un censimento.

    Le due guardie sono parametrizzate sulla scoperta: se questa torna vuota
    — `src/pge` spostato, `tests/` riorganizzato — pytest le salta e la suite
    resta verde sopra un presidio che non esiste più. Il numero è basso di
    proposito: oggi le coppie sono una sessantina, e un valore stretto
    diventerebbe una trascrizione da aggiornare a ogni modulo nuovo.
    """
    coppie = _coppie()

    assert len(coppie) >= 20, (
        f"la scoperta trova {len(coppie)} coppie test/modulo: troppo poche "
        "perché `tests/<area>/test_<modulo>.py` sia ancora la convenzione "
        "che questa suite legge. Controlla _coppie()."
    )


# =============================================================================
# 3. I CRITERI DISCRIMINANO — altrimenti le guardie sono verdi a vuoto
# =============================================================================
# Una guardia che non sa riconoscere ciò che cerca non fallisce: tace. Questi
# test la misurano sulle grafie reali, in tutte e due le direzioni, così che
# a indebolirla qualcosa suoni.

@pytest.mark.parametrize('sorgente', [
    'import pge.parameters.parser',
    'import pge.parameters.parser as p',
    'from pge.parameters.parser import GranularParser',
    'from pge.parameters import parser',
    'from pge.parameters import parser as p',
    'import importlib\nx = importlib.import_module("pge.parameters.parser")',
    'from importlib import import_module\nx = import_module'
    '("pge.parameters.parser")',
    'def f():\n    from pge.parameters.parser import GranularParser\n'
    '    return GranularParser',
])
def test_il_criterio_riconosce_le_grafie_dell_import(sorgente):
    """Le grafie con cui la suite importa davvero, compresa quella dinamica."""
    assert _importa(ast.parse(sorgente), 'pge.parameters.parser')


@pytest.mark.parametrize('sorgente', [
    # Il prefisso senza punto: un altro modulo, stessa radice nel nome.
    'from pge.parameters import parameter_definitions',
    'import pge.parameters.parameter_definitions',
    'from pge.parameters.parameter_definitions import ParameterBounds',
    # Omonimo in un altro package.
    'from pge.rendering import parameter',
    # Una stringa che nessuno importa.
    's = "pge.parameters.parameter"',
])
def test_il_criterio_non_scambia_un_omonimo_per_il_modulo(sorgente):
    """`parameter_definitions` non è `parameter`, e il punto è il criterio.

    Senza il punto obbligatorio dopo il prefisso, `test_parameter.py`
    passerebbe la prima guardia grazie a un import che riguarda un altro
    file: la guardia direbbe di sorvegliare un modulo mai toccato.
    """
    assert not _importa(ast.parse(sorgente), 'pge.parameters.parameter')


def test_il_criterio_vede_la_riscrittura():
    """Una classe pubblica del modulo, ridefinita a livello di modulo."""
    tree = ast.parse('class GranularParser:\n    def parse(self):\n'
                     '        return 1\n')

    assert _nomi_di_modulo(tree) & {'GranularParser'}


def test_il_criterio_non_accusa_le_finte_locali():
    """Una classe finta dentro una fixture non prende il posto del modulo.

    È il pattern normale di mezza suite; contarlo renderebbe la guardia
    rumorosa dove non ha niente da dire, e una guardia rumorosa la si spegne.
    """
    tree = ast.parse(
        'import pytest\n'
        'class TestX:\n'
        '    def test_a(self):\n'
        '        class GranularParser: pass\n'
        '        assert GranularParser\n'
    )

    assert 'GranularParser' not in _nomi_di_modulo(tree)


def test_il_criterio_guarda_solo_i_nomi_pubblici(tmp_path):
    """I privati del modulo non sono la sua superficie.

    Un `_helper` che un test ridefinisce non è la riscrittura che la #274
    descrive: la copia che inganna chi legge porta il nome che il resto del
    repo importa.
    """
    modulo = tmp_path / 'm.py'
    modulo.write_text('class Pubblica: pass\n'
                      'def _privata(): pass\n'
                      'COSTANTE = 3\n', encoding='utf-8')

    assert _nomi_pubblici(str(modulo)) == {'Pubblica'}


# =============================================================================
# 4. NESSUN PERCORSO DI UN'ALTRA MACCHINA
# =============================================================================
# Terzo residuo censito dalla #274, e della stessa famiglia: muto per
# costruzione. `sys.path.insert(0, '/home/claude')` non fallisce da nessuna
# parte — inserire un path inesistente è legale — e `pytest.ini` (`pythonpath
# = . src`) fa comunque riuscire gli import. Restava lì a dire da quale
# macchina il file era arrivato, e chi lo leggeva poteva crederlo necessario:
# in `test_parameter.py` la riga stava proprio dentro `_import_real_parameter()`,
# cioè l'unica funzione del file che toccava produzione.

def _percorsi_assoluti_in_sys_path(tree):
    """I literal assoluti passati a `<qualcosa>.path.insert/append(...)`.

    Il criterio è la forma della chiamata più il letterale: `sys.path` e
    `_sys.path` (l'alias che `test_parameter.py` usava) passano di qui, e ciò
    che si accusa è solo una stringa costante che comincia per `/`. I path
    calcolati — `os.path.abspath(...)`, `str(REPO_ROOT / 'utils')`, che sono
    la forma di tutti gli altri inserimenti della suite — non sono
    `ast.Constant` e non entrano.
    """
    trovati = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute)
                and func.attr in ('insert', 'append')):
            continue
        base = func.value
        if not (isinstance(base, ast.Attribute) and base.attr == 'path'):
            continue
        for arg in node.args:
            if (isinstance(arg, ast.Constant)
                    and isinstance(arg.value, str)
                    and os.path.isabs(arg.value)):
                trovati.append(arg.value)
    return trovati


def _file_di_test():
    for radice, cartelle, files in os.walk(TESTS_DIR):
        cartelle[:] = [c for c in cartelle if c != '__pycache__']
        for nome in sorted(files):
            if nome.endswith('.py'):
                yield os.path.relpath(os.path.join(radice, nome), TESTS_DIR)


@pytest.mark.parametrize('rel', sorted(_file_di_test()))
def test_nessun_test_inserisce_in_sys_path_un_percorso_assoluto(rel):
    """Un path assoluto scritto a mano vale su una macchina sola.

    Dove vale non serve (ci pensa `pytest.ini`), e dove non vale non fallisce:
    inserisce una cartella inesistente e l'import riesce lo stesso. È la forma
    più pura del difetto che la #274 registra — una riga che non può parlare.
    """
    trovati = _percorsi_assoluti_in_sys_path(
        _albero(os.path.join(TESTS_DIR, rel)))

    assert not trovati, (
        f"tests/{rel} inserisce in sys.path {trovati}: percorsi di un'altra "
        "macchina. La radice del repo e `src/` ci sono già via `pytest.ini` "
        "(`pythonpath = . src`) e `tests/conftest.py`; un path da calcolare "
        "si scrive a partire da `__file__`. Vedi issue #274."
    )


def test_il_criterio_vede_i_percorsi_di_un_altra_macchina():
    """Le due grafie censite, alias compreso."""
    sorgente = (
        "import sys\n"
        "sys.path.insert(0, '/home/claude')\n"
        "import sys as _sys\n"
        "_sys.path.insert(0, '/Users/tizio/github/PythonGranularEngine/src')\n"
    )

    assert len(_percorsi_assoluti_in_sys_path(ast.parse(sorgente))) == 2


def test_il_criterio_non_accusa_i_percorsi_calcolati():
    """La forma che usa il resto della suite resta legittima."""
    sorgente = (
        "import os, sys\n"
        "sys.path.insert(0, os.path.abspath(\n"
        "    os.path.join(os.path.dirname(__file__), '../src')))\n"
        "sys.path.insert(1, os.path.join(REPO_ROOT, 'utils'))\n"
        "sys.path.insert(0, str(REPO_ROOT / 'utils'))\n"
    )

    assert _percorsi_assoluti_in_sys_path(ast.parse(sorgente)) == []
