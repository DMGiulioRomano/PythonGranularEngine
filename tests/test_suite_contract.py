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

La #274 ha misurato **due** file della suite che non spostano di una riga la
copertura del modulo che nominano; il terzo — `test_probability_gate.py` — lo
ha trovato questa guardia, e la sua misura è di qui. Non è un buco di
copertura — quei moduli sono coperti dal *resto* della suite, al 97%, al 95%
e all'85% — ma un'esca: chi modifica `parameter.py` apre `test_parameter.py`,
legge 72 test sul comportamento di `Parameter`, e sta leggendo il
comportamento di un'altra classe che si chiama allo stesso modo. Nella PR
#273 è successo per tre volte di fila: i due file non hanno potuto né
confermare né smentire, e sono rimasti verdi.

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

Secondo limite, della stessa famiglia: la riscrittura si riconosce come
`class` o `def`, non come alias. `GranularParser = _Finto` non è né l'uno né
l'altro e passa. Accusare le assegnazioni renderebbe rosso anche
`Stream = pge.core.stream.Stream`, che è il modulo vero e non una copia, e
una guardia rumorosa la si spegne. Annidare la copia, invece, non basta più a
farla passare: vedi `_nomi_di_modulo`.

Terzo limite, sul lato del sorgente: la superficie è ciò che il modulo
*definisce*, non ciò che riespone importandolo — vedi `_nomi_pubblici`.

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

def _sorgente_di(puntato, src=None):
    """Il file che il modulo `puntato` nomina.

    Una grafia sola, perche' la leggono in due: la scoperta, che la usa per
    decidere se la coppia esiste, e la guardia sulla riscrittura, che deve
    aprire quello stesso file. Scritta due volte, il giorno in cui il layout
    di `src/` cambia una delle due resta indietro in silenzio — e quella che
    resta indietro e' la guardia, cioe' la meta' che deve parlare.

    `src` serve soltanto ai test della scoperta, che le danno un albero
    finto: in produzione la radice e' una sola.
    """
    return os.path.join(src or SRC_PGE, *puntato.split('.')[1:]) + '.py'


def _coppie(tests_dir=None, src=None):
    """`(relpath sotto tests/, modulo puntato, path del sorgente)`.

    Solo dove il modulo nominato esiste davvero: un `test_<x>.py` che non
    corrisponde a nessun `<x>.py` non promette niente e non è affare di
    questa suite. È quel controllo — non la profondità — a decidere: una
    cartella di `tests/` che non corrisponde a un package di `pge` non
    produce coppie perché il sorgente non c'è, non perché qualcuno l'abbia
    saltata.

    La corrispondenza vale quindi a **qualsiasi** profondità:
    `tests/<a>/<b>/test_<m>.py` ↔ `src/pge/<a>/<b>/<m>.py` è la stessa
    promessa di un livello solo, e leggerne uno soltanto era un criterio più
    stretto di quello dichiarato, messo — come già due volte in questa suite
    — dalla parte che assolve: un file annidato sarebbe uscito dalla
    sorveglianza in silenzio, senza nemmeno finire in
    `SIMULAZIONI_DICHIARATE`. `tests/rendering/renderers/` esiste già (oggi
    con il solo `__init__.py`), e `pge` non ha ancora un package annidato:
    misurato, la lettura larga non aggiunge nessuna coppia alle 69 di oggi.

    `tests_dir` e `src` servono soltanto ai test della scoperta, che le
    danno un albero finto.
    """
    tests_dir = tests_dir or TESTS_DIR
    trovate = []
    for radice, cartelle, files in os.walk(tests_dir):
        cartelle[:] = [c for c in cartelle if c != '__pycache__']
        area = os.path.relpath(radice, tests_dir)
        area = '' if area == '.' else area
        pezzi = area.split(os.sep) if area else []
        for nome in sorted(files):
            if not (nome.startswith('test_') and nome.endswith('.py')):
                continue
            modulo = nome[len('test_'):-len('.py')]
            puntato = '.'.join(['pge'] + pezzi + [modulo])
            sorgente = _sorgente_di(puntato, src)
            if not os.path.isfile(sorgente):
                continue
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
    """Classi e funzioni che **all'import** finiscono nel namespace del file.

    Il criterio non è la colonna ma l'esecuzione: una classe finta dentro una
    fixture è un dettaglio di un test e non entra, una classe finta che gira
    all'import prende il posto del modulo vero per tutto il file — ed è
    quest'ultima la forma che hanno tutte e tre le riscritture censite.

    Le due cose non coincidono con `tree.body`, e la differenza è esattamente
    la grafia che batte **tutte e due** le guardie in una volta:

        try:
            from pge.parameters.parser import GranularParser
        except ImportError:
            class GranularParser: ...

    lì l'import c'è (prima metà verde) e il nome è indentato di quattro spazi
    (seconda metà verde), mentre all'import il file può benissimo girare
    sulla copia. Si scende quindi in ogni corpo di istruzione — `if`, `try`,
    gli `except`, `with`, i cicli — e ci si ferma sul primo `def` o `class`,
    perché da lì in giù non è più livello di modulo.

    Limite dichiarato: un alias (`GranularParser = _Finto`) non è né un `def`
    né un `class` e non entra. Accusare le assegnazioni renderebbe rosso
    anche `Stream = pge.core.stream.Stream`, che è il modulo vero e non una
    copia, e una guardia rumorosa la si spegne.
    """
    nomi = set()

    def visita(corpo):
        for n in corpo:
            if isinstance(n, (ast.ClassDef, ast.FunctionDef,
                              ast.AsyncFunctionDef)):
                nomi.add(n.name)
                continue
            for figlio in ast.iter_child_nodes(n):
                if isinstance(figlio, ast.stmt):
                    visita([figlio])
                else:
                    # `except ...:` e `case ...:` non sono istruzioni, ma un
                    # corpo ce l'hanno; un'espressione no (il `body` di una
                    # lambda è un'espressione sola, non una lista).
                    annidato = getattr(figlio, 'body', None)
                    if isinstance(annidato, list):
                        visita(annidato)

    visita(tree.body)
    return nomi


def _nomi_pubblici(path):
    """Classi e funzioni pubbliche che il modulo **definisce** al primo livello.

    «Primo livello» vuol dire qui la stessa cosa che vuol dire per il file di
    test — ciò che gira all'import — e si legge con la stessa `_nomi_di_modulo`,
    per l'argomento che `_sorgente_di` fa per il percorso: scritto due volte,
    il criterio diverge, e quella che resta indietro è la metà che deve
    parlare. Qui la copia stretta stava proprio dalla parte del sorgente, cioè
    dove restringerla *assolve*. Un modulo che definisce la sua classe dentro
    un `try:` — il fallback di una dipendenza opzionale, la forma che questo
    repo ha per numpy e matplotlib — la teneva fuori dalla propria superficie,
    e un test che la riscriveva a livello di modulo passava la seconda guardia
    in silenzio: il falso negativo esatto di cui questa suite parla.

    Oggi nessun modulo di `pge` definisce un nome pubblico in quella
    posizione, quindi la lettura larga non cambia nessun verdetto — chiude il
    buco prima che qualcuno ci cada dentro.

    Le costanti restano fuori di proposito: un test che dichiara un
    `DENSITY_BOUNDS` accanto a quello del modulo sta scrivendo una fixture,
    non una riscrittura, e accusarlo renderebbe la guardia rumorosa proprio
    dove non ha niente da dire.

    Fuori restano anche i nomi che il modulo **riespone** importandoli:
    `pge.parameters.parser` importa `Envelope`, e `parser.Envelope` esiste,
    ma la classe è di `pge.envelopes.envelope`. Un test che ne mette una
    finta a livello di modulo sta facendo il doppio di un collaboratore —
    pratica normale — non la riscrittura del modulo che il suo nome promette,
    e la seconda guardia lo accuserebbe dicendo che a definirlo è `parser`.
    Misurato: sui 66 file sorvegliati la distinzione non cambia nessun
    verdetto, e i due dove cambierebbe sono già dichiarati qui sopra.
    """
    return {n for n in _nomi_di_modulo(_albero(path))
            if not n.startswith('_')}


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
    sorgente = _sorgente_di(puntato)
    doppioni = _riscritture(rel_test, sorgente)

    assert not doppioni, (
        f"tests/{rel_test} ridefinisce a livello di modulo "
        f"{sorted(doppioni)}, che `{puntato}` definisce. Chi legge il file "
        "crede di leggere il comportamento del modulo e legge quello della "
        "copia. Se la simulazione è voluta, dichiarala in "
        "SIMULAZIONI_DICHIARATE. "
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
    dice. È il canarino di `_coppie()`, e solo di quella: le due guardie qui
    sopra leggono `_sorvegliate()`, che è `_coppie()` filtrata, e una
    `_sorvegliate()` vuota lascia verde anche questo test — il suo pavimento
    è `test_le_guardie_girano_su_tutte_le_coppie_sorvegliate`.
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

    `_coppie()` è la materia prima delle due guardie: se torna vuota —
    `src/pge` spostato, `tests/` riorganizzato — non resta niente da
    sorvegliare. Il numero è basso di proposito: oggi le coppie sono una
    sessantina, e un valore stretto diventerebbe una trascrizione da
    aggiornare a ogni modulo nuovo.

    Questo pavimento sta sotto la scoperta, non sotto il `parametrize`: le
    due guardie leggono `_sorvegliate()`, che è `_coppie()` meno le
    dichiarate, e fra le due c'è un filtro che questo test non attraversa.
    Il pavimento di quel filtro è il test qui sotto.
    """
    coppie = _coppie()

    assert len(coppie) >= 20, (
        f"la scoperta trova {len(coppie)} coppie test/modulo: troppo poche "
        "perché `tests/<area>/test_<modulo>.py` sia ancora la convenzione "
        "che questa suite legge. Controlla _coppie()."
    )


def test_le_guardie_girano_su_tutte_le_coppie_sorvegliate():
    """Il pavimento sotto la scoperta che le due guardie leggono davvero.

    Le scoperte di questo file sono tre — `_coppie()`, `_sorvegliate()` e
    `_file_di_test()` — e a parametrizzare sono la seconda e la terza. Il
    pavimento è nato sotto la prima e sotto la terza, cioè sotto una delle
    due che contano: `_sorvegliate()` è la sola scoperta che parametrizza
    senza averne uno, ed è quella su cui girano le due guardie che sono il
    punto della suite.

    Il buco non era teorico. Misurato mutando il sorgente: con
    `_sorvegliate()` che torna vuota pytest stampa `got empty parameter set`
    per tutte e due le guardie ed **esce 0**; con una coppia sola ne gira una
    su 66 e stampa verde. In nessuno dei due casi parlava qualcun altro —
    `test_la_scoperta_vede_la_suite` misura `_coppie()`, che è intatta, e il
    canarino delle dichiarate pure.

    Le due metà non si coprono a vicenda, e la misura dice quale fa il
    lavoro. La **relazione** è quella che morde: fra `_coppie()` e il
    `parametrize` c'è un filtro, l'unica cosa che ha il diritto di togliere è
    `SIMULAZIONI_DICHIARATE`, e un filtro che cominciasse a scartare file
    sorvegliati li farebbe uscire in silenzio, senza nemmeno passare dalla
    lista — il falso negativo che questa suite esiste per togliere. Tutte e
    quattro le mutazioni provate (vuota, una coppia sola, le prime trenta,
    due aree su dieci) sono rosse su di lei, e le ultime due **solo** su di
    lei. È derivata dalle due scoperte e dalla lista, non trascritta, quindi
    non invecchia a ogni modulo nuovo.

    Il **conto** resta per l'unico caso in cui il filtro fa esattamente ciò
    che dichiara e il `parametrize` si svuota lo stesso: la lista che cresce
    fino a inghiottire la suite. Lì la relazione tace per costruzione
    (`coppie - dichiarate` è davvero vuoto) e il canarino qui sopra pure,
    perché ogni riga aggiunta viola per davvero. È l'unico assert del file
    che metta un limite a quanto `SIMULAZIONI_DICHIARATE` può allargarsi —
    una lista che è debito, e che dovrebbe accorciarsi.
    """
    coppie = {rel for rel, _, _ in _coppie()}
    sorvegliate = {rel for rel, _ in _sorvegliate()}

    assert len(sorvegliate) >= 20, (
        f"le due guardie girerebbero su {len(sorvegliate)} coppie: troppo "
        "poche perché un `parametrize` vuoto è uno skip, non un rosso, e la "
        "suite resterebbe verde sopra un presidio che non c'è più. "
        "Controlla _sorvegliate()."
    )
    assert sorvegliate == coppie - set(SIMULAZIONI_DICHIARATE), (
        "_sorvegliate() non è `_coppie()` meno le dichiarate: fuori dalla "
        "sorveglianza finiscono anche "
        f"{sorted(coppie - sorvegliate - set(SIMULAZIONI_DICHIARATE))}, e "
        "dentro "
        f"{sorted(sorvegliate - coppie)}. Un file che esce di lì esce in "
        "silenzio, senza passare da SIMULAZIONI_DICHIARATE."
    )


def test_la_scoperta_segue_i_package_annidati(tmp_path):
    """`<area>` può essere un package annidato, e la promessa è la stessa.

    `tests/<a>/<b>/test_<m>.py` promette `src/pge/<a>/<b>/<m>.py` esattamente
    come un livello solo. Fermarsi al primo livello era un criterio più
    stretto di quello dichiarato, messo dalla parte che assolve: un file
    annidato usciva dalla sorveglianza in silenzio, senza nemmeno finire in
    `SIMULAZIONI_DICHIARATE` — cioè il falso negativo che questa suite
    esiste per togliere, sulla sua stessa scoperta.

    Su `tests/` non è un caso di scuola: `tests/rendering/renderers/` esiste
    già, oggi con il solo `__init__.py`. Il verdetto di oggi non cambia (`pge`
    non ha package annidati, le coppie restano 69), quindi il buco si chiude
    prima che qualcuno ci cada dentro — l'albero qui è finto proprio perché
    l'albero vero non può ancora misurarlo.
    """
    tests = tmp_path / 'tests' / 'rendering' / 'renderers'
    tests.mkdir(parents=True)
    (tests / 'test_foo.py').write_text('', encoding='utf-8')
    (tests / 'test_senza_modulo.py').write_text('', encoding='utf-8')
    src = tmp_path / 'src' / 'pge' / 'rendering' / 'renderers'
    src.mkdir(parents=True)
    (src / 'foo.py').write_text('', encoding='utf-8')

    coppie = _coppie(str(tmp_path / 'tests'), str(tmp_path / 'src' / 'pge'))

    assert coppie == [(
        os.path.join('rendering', 'renderers', 'test_foo.py'),
        'pge.rendering.renderers.foo',
        str(src / 'foo.py'),
    )], coppie


def test_la_scoperta_non_inventa_coppie_dove_il_modulo_non_c_e(tmp_path):
    """Il contrappeso della profondità: a decidere resta il sorgente.

    Allargare la lettura senza questo sarebbe la guardia rumorosa che la
    suite dichiara tre volte di non voler essere: `tests/export/fixtures/`
    non è un package di `pge`, e una coppia lì dentro accuserebbe un file di
    non importare un modulo che non esiste.
    """
    tests = tmp_path / 'tests' / 'export' / 'fixtures' / 'sv_reference'
    tests.mkdir(parents=True)
    (tests / 'test_qualcosa.py').write_text('', encoding='utf-8')
    (tmp_path / 'src' / 'pge').mkdir(parents=True)

    assert _coppie(str(tmp_path / 'tests'),
                   str(tmp_path / 'src' / 'pge')) == []


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
    # Omonimo per via relativa: non nomina nessun modulo di `pge`, e non ha
    # nemmeno un modulo da leggere. La grafia e' scrivibile — `tests/e2e/` e
    # `tests/rendering/renderers/` sono package — e senza la guardia su
    # `node.level` la prima meta' non risponde: scoppia.
    'from . import parameter',
    # Una stringa che nessuno importa.
    's = "pge.parameters.parameter"',
    # La stessa stringa dentro una chiamata che non e' `import_module`:
    # `patch` nomina il modulo, non e' una delle quattro grafie, e questa
    # suite la scrive 264 volte.
    "from unittest.mock import patch\n"
    "patch('pge.parameters.parameter.Parameter')\n",
    "from unittest.mock import patch\n"
    "with patch('pge.parameters.parameter.resolve_param'):\n    pass\n",
])
def test_il_criterio_non_scambia_un_omonimo_per_il_modulo(sorgente):
    """`parameter_definitions` non è `parameter`, e il punto è il criterio.

    Senza il punto obbligatorio dopo il prefisso, `test_parameter.py`
    passerebbe la prima guardia grazie a un import che riguarda un altro
    file: la guardia direbbe di sorvegliare un modulo mai toccato.

    Le ultime due righe misurano l'altro filtro della grafia dinamica: la
    stringa vale come import solo dentro `import_module`. Togliere
    `nome != 'import_module'` lasciava il file **tutto verde**, e da li' in
    poi qualunque chiamata che nominasse il modulo in una stringa contava
    come import — `patch('pge.<area>.<modulo>....')`, che in questa suite
    sono 264 righe. E' la direzione che fa danno: un file che riscrive il
    modulo e si limita a spiare un nome con `patch` passerebbe la prima
    meta', cioe' proprio la popolazione che questa suite esiste per trovare.
    """
    assert not _importa(ast.parse(sorgente), 'pge.parameters.parameter')


def test_il_criterio_vede_la_riscrittura():
    """Una classe pubblica del modulo, ridefinita a livello di modulo."""
    tree = ast.parse('class GranularParser:\n    def parse(self):\n'
                     '        return 1\n')

    assert _nomi_di_modulo(tree) & {'GranularParser'}


@pytest.mark.parametrize('sorgente', [
    # La grafia che batte tutte e due le guardie in una volta: l'import c'è,
    # e il nome è indentato.
    'try:\n    from pge.parameters.parser import GranularParser\n'
    'except ImportError:\n    class GranularParser: pass\n',
    'import sys\nif sys.version_info >= (3, 12):\n'
    '    class GranularParser: pass\n',
    'import sys\nif False:\n    pass\nelse:\n'
    '    class GranularParser: pass\n',
    'try:\n    pass\nfinally:\n    class GranularParser: pass\n',
    'import contextlib\nwith contextlib.suppress(Exception):\n'
    '    class GranularParser: pass\n',
    'for _ in (1,):\n    def GranularParser(): pass\n',
])
def test_il_criterio_vede_la_riscrittura_annidata(sorgente):
    """Indentare la copia non la rende un dettaglio locale.

    Questi corpi girano all'import: quando finiscono, il namespace del file
    ha dentro la copia, e i test che stanno sotto la usano al posto del
    modulo — che è la definizione stessa della riscrittura. Contare solo
    `tree.body` lasciava fuori proprio la forma che passa anche la prima
    guardia, cioè l'unica capace di far tacere le due metà insieme.
    """
    assert 'GranularParser' in _nomi_di_modulo(ast.parse(sorgente))


@pytest.mark.parametrize('sorgente', [
    # Dentro un metodo: il pattern normale di mezza suite.
    'class TestX:\n    def test_a(self):\n'
    '        class GranularParser: pass\n',
    # Dentro una funzione di modulo: esiste solo mentre la funzione gira.
    'def fabbrica():\n    class GranularParser: pass\n'
    '    return GranularParser\n',
    # Dentro una fixture.
    'import pytest\n@pytest.fixture\ndef parser():\n'
    '    class GranularParser: pass\n    return GranularParser()\n',
])
def test_il_criterio_non_accusa_le_finte_annidate_in_una_funzione(sorgente):
    """Il confine è il primo `def`/`class`, non l'indentazione.

    Scendere anche lì renderebbe rossa mezza suite su classi che nessuno
    vede fuori dalla chiamata, e una guardia rumorosa la si spegne.
    """
    assert 'GranularParser' not in _nomi_di_modulo(ast.parse(sorgente))


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


def test_la_superficie_del_modulo_comprende_le_definizioni_all_import(tmp_path):
    """Anche il sorgente ha un «livello di modulo» che non è la prima colonna.

    Il fallback di una dipendenza opzionale definisce la classe dentro un
    `try:`, e all'import quella classe è la superficie del modulo come
    qualunque altra. Leggendo il solo `tree.body` restava fuori, e un test
    che la riscriveva a livello di modulo passava la seconda guardia: il
    criterio stretto stava dalla parte dove restringere vuol dire assolvere.
    """
    modulo = tmp_path / 'm.py'
    modulo.write_text(
        'try:\n'
        '    from numpy import Finestra\n'
        'except ImportError:\n'
        '    class Finestra: pass\n'
        'class Pubblica: pass\n',
        encoding='utf-8')

    assert _nomi_pubblici(str(modulo)) == {'Finestra', 'Pubblica'}


def test_la_superficie_del_modulo_e_quella_definita_non_quella_riesposta(
        tmp_path):
    """Un nome che il modulo importa non è suo, ed è un'esclusione voluta.

    `pge.parameters.parser` riespone `Envelope`, che però definisce
    `pge.envelopes.envelope`: un test che ne mette una finta a livello di
    modulo sta facendo il doppio di un collaboratore, non la riscrittura del
    modulo che il suo nome promette. Accusarlo sarebbe rumore, e per giunta
    con un messaggio falso — direbbe che a definire quel nome è `parser`.

    È l'altra faccia del test qui sopra: là la lettura del sorgente si
    allarga perché restringere assolve, qui si ferma perché allargare accusa
    chi non c'entra. Misurato sui 66 file sorvegliati: la distinzione non
    cambia nessun verdetto.
    """
    modulo = tmp_path / 'm.py'
    modulo.write_text('from pge.envelopes.envelope import Envelope\n'
                      'class Propria: pass\n', encoding='utf-8')

    assert _nomi_pubblici(str(modulo)) == {'Propria'}


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

def _nomi_di_sys_path(tree):
    """I nomi con cui il file chiama `sys.path` senza passare per `sys`.

    `from sys import path` lega la lista a un nome semplice, e da lì
    `path.insert(0, '/home/claude')` è la stessa riga di tutte le altre —
    mentre `_e_un_path`, che cerca un attributo, non la vede. Il nome si
    raccoglie dall'import invece di accusare ogni `path` che capiti: un
    `path` qualunque è una variabile locale, e una guardia rumorosa la si
    spegne. Il filtro ha due metà per lo stesso motivo, e ciascuna tiene
    fuori una grafia diversa: l'import dev'essere **di** `path`, altrimenti
    `from sys import argv` farebbe di `argv` un alias della lista, e
    dev'essere **da** `sys`, altrimenti `from os import path` — la grafia
    più comune che leghi quel nome — farebbe di `os.path` la lista di
    `sys`, e un `path.append('/Users/tizio/repo')` sarebbe un rosso con
    sopra un messaggio che parla di `sys.path`.
    """
    nomi = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.ImportFrom) and not node.level
                and node.module == 'sys'):
            nomi.update(a.asname or a.name
                        for a in node.names if a.name == 'path')
    return nomi


def _nomi_del_modulo_sys(tree):
    """I nomi con cui il file chiama il modulo `sys`.

    `sys` ci sta sempre — e' il nome del modulo, e un file che lo usa senza
    importarlo lo prende comunque da li' — accanto agli alias che l'import
    dichiara: `import sys as _sys`, la grafia che `_import_real_parameter()`
    usava, e `from os import sys as _s`, che lega lo stesso modulo per
    un'altra strada. L'esempio del secondo ramo dev'essere quello, con
    l'alias: `from os import sys` senza alias lega il nome `sys`, che il
    valore di partenza ha gia', quindi non e' la riga che quel ramo serve —
    e un esempio che non lo attraversa e' un ramo dichiarato e non misurato.

    Anche qui il filtro ha due metà: l'import dev'essere **di** `sys`, o
    `import os` farebbe di `os.path` la lista di `sys`.
    """
    nomi = {'sys'}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            nomi.update(a.asname or a.name
                        for a in node.names if a.name == 'sys')
    return nomi


def _e_un_path(nodo, moduli=('sys',), alias=()):
    """`sys.path`: non qualunque cosa si chiami `path`, e nemmeno
    qualunque cosa stia su `sys`.

    Due grafie, come il bersaglio dell'istruzione: l'attributo — `sys.path`,
    l'alias `_sys.path` che `test_parameter.py` usava, `os.sys.path` che e'
    lo stesso modulo per un'altra strada — e il nome semplice legato da
    `from sys import path` (vedi `_nomi_di_sys_path`).

    Nell'attributo si chiedono tutti e due i pezzi, non il solo `path`.
    Accusare ogni attributo che porti quel nome rende rosso un
    `cfg.path = '/tmp/x'`, che non e' `sys.path` e non e' la riga che questa
    sezione toglie — con sopra un messaggio che parla di `sys.path` e nomina
    una issue che non c'entra. E' lo stesso contrappeso che il nome semplice
    ha gia': il nome si raccoglie dall'import invece di darlo per scontato,
    perche' una guardia rumorosa la si spegne. Il principio era scritto per
    uno dei due estremi e valeva per uno solo dei due.
    """
    if isinstance(nodo, ast.Attribute) and nodo.attr == 'path':
        base = nodo.value
        if isinstance(base, ast.Name):
            return base.id in moduli
        return isinstance(base, ast.Attribute) and base.attr in moduli
    return isinstance(nodo, ast.Name) and nodo.id in alias


def _letterali_assoluti(nodo):
    """I letterali assoluti che compaiono dentro l'espressione inserita.

    Si guarda tutta l'espressione, non la sua sola cima: liste, tuple,
    concatenazioni e **chiamate**. Riconoscere le tre forme strutturali e
    fermarsi lì era, sul valore, la stessa distrazione che fermarsi a
    `insert` era sull'istruzione: `os.path.join('/Users/tizio/repo', 'src')`
    è la stessa riga di `'/Users/tizio/repo/src'`, ed è una chiamata, quindi
    passava.

    I percorsi calcolati restano leciti perché non contengono nessun
    letterale assoluto, non perché siano chiamate:
    `os.path.abspath(os.path.join(os.path.dirname(__file__), '../src'))` e
    `str(REPO_ROOT / 'utils')` — la forma di tutti gli altri inserimenti
    della suite — non ne hanno uno. È il letterale il criterio, in qualsiasi
    posizione stia.
    """
    return [n.value for n in ast.walk(nodo)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and os.path.isabs(n.value)]


def _percorsi_assoluti_in_sys_path(tree):
    """I literal assoluti che un file aggiunge a `sys.path`, in ogni grafia.

    Il criterio è la forma dell'istruzione più il letterale. Le grafie sono
    quattro e valgono tutte la stessa riga — `insert`/`append`/`extend`,
    `sys.path += [...]`, `sys.path[:0] = [...]` e la riassegnazione secca —
    perché una guardia che ne riconoscesse una sola si spegnerebbe da sé al
    primo `+=`: sarebbe la stessa riga muta che questa sezione toglie, con
    sopra un test verde che dice il contrario.

    Lo stesso vale per i due estremi dell'istruzione, che hanno avuto la
    stessa distrazione ciascuno: il bersaglio può essere un nome semplice
    (`from sys import path`, vedi `_nomi_di_sys_path`) e il letterale può
    stare dentro una chiamata (vedi `_letterali_assoluti`). Riconoscere solo
    la grafia centrale lasciava fuori le due riscritture più ovvie della
    stessa riga.

    Il bersaglio ha pero' anche il verso opposto, ed e' l'unico posto dove
    questa sezione puo' accusare chi non c'entra: `sys.path` si chiede al
    modulo *e* al campo (`_e_un_path`), perche' `cfg.path` non e' `sys.path`
    e un rosso li' parlerebbe di una riga che il file non ha.
    """
    alias = _nomi_di_sys_path(tree)
    moduli = _nomi_del_modulo_sys(tree)
    trovati = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if (isinstance(func, ast.Attribute)
                    and func.attr in ('insert', 'append', 'extend')
                    and _e_un_path(func.value, moduli, alias)):
                for arg in node.args:
                    trovati.extend(_letterali_assoluti(arg))
        elif isinstance(node, ast.AugAssign):
            if _e_un_path(node.target, moduli, alias):
                trovati.extend(_letterali_assoluti(node.value))
        elif isinstance(node, ast.Assign):
            for bersaglio in node.targets:
                # `sys.path[:0] = [...]` è un'assegnazione a una fetta, e la
                # fetta di `sys.path` è `sys.path`.
                if isinstance(bersaglio, ast.Subscript):
                    bersaglio = bersaglio.value
                if _e_un_path(bersaglio, moduli, alias):
                    trovati.extend(_letterali_assoluti(node.value))
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


def test_la_scoperta_vede_i_file_della_suite():
    """Il pavimento della quarta sezione, per l'argomento della prima.

    La guardia qui sopra è parametrizzata su `_file_di_test()` esattamente
    come le due della prima sezione lo sono su `_sorvegliate()`, e un
    parametrize vuoto non è un rosso: pytest lo salta e la suite resta verde
    sopra un presidio che non esiste più. L'argomento — scritto qui per
    intero — vale per ogni scoperta che parametrizza, e le scoperte di
    questo file sono tre: `_coppie()`, il `_sorvegliate()` che la filtra e
    questa. Il loro pavimento sta rispettivamente in
    `test_la_scoperta_vede_la_suite`,
    `test_le_guardie_girano_su_tutte_le_coppie_sorvegliate` e qui.

    Il numero è basso di proposito, come l'altro: oggi i file sono un
    centinaio e mezzo, e un valore stretto diventerebbe una trascrizione da
    aggiornare a ogni test nuovo. Accanto, due ancore, perché il conto è
    cieco a due spostamenti diversi e ciascuna ne vede uno.

    La prima è questo file, chiesto a `__file__` invece che trascritto: un
    filtro che smettesse di vedere i `.py` della radice di `tests/`
    passerebbe il pavimento e non lui.

    La seconda è la sola cosa che distingue questa scoperta dalle altre due:
    legge **ogni** `.py`, non i soli `test_*.py`, e quel «ogni» era scritto
    e non misurato. `__file__` non poteva dirlo — si chiama `test_…` anche
    lui — quindi la mutazione che restringe `_file_di_test()` ai file di
    test lasciava il file **tutto verde**, e con lei se ne andava
    `tests/conftest.py`: l'unico file della suite che scriva davvero in
    `sys.path`, e il posto dove quella riga naturalmente vive. Il criterio è
    l'estensione, quindi l'ancora chiede che almeno un `.py` non sia un file
    di test, invece di nominarne uno — un nome trascritto sarebbe la lista
    che invecchia da sola.
    """
    files = sorted(_file_di_test())

    assert len(files) >= 50, (
        f"la scoperta trova {len(files)} file sotto tests/: troppo pochi "
        "perché la guardia sui percorsi assoluti stia ancora leggendo la "
        "suite. Controlla _file_di_test()."
    )
    assert os.path.relpath(__file__, TESTS_DIR) in files, (
        "_file_di_test() non trova nemmeno il file che la contiene: la "
        "guardia sui percorsi assoluti sta leggendo un'altra cartella."
    )
    assert [f for f in files
            if not os.path.basename(f).startswith('test_')], (
        "_file_di_test() non trova nessun `.py` che non sia un file di "
        "test: il criterio della quarta sezione è l'estensione, non il "
        "prefisso. Fuori dalla guardia sui percorsi assoluti finirebbe "
        "`tests/conftest.py`, che in `sys.path` ci scrive davvero, ed è il "
        "posto dove quella riga naturalmente vive. Controlla "
        "_file_di_test()."
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


@pytest.mark.parametrize('sorgente', [
    "import sys\nsys.path.append('/home/claude')\n",
    "import sys\nsys.path.extend(['/home/claude'])\n",
    "import sys\nsys.path += ['/home/claude']\n",
    "import sys\nsys.path[:0] = ['/home/claude']\n",
    "import sys\nsys.path[0:0] = ('/home/claude',)\n",
    "import sys\nsys.path = ['/home/claude'] + sys.path\n",
    "import sys as _sys\n_sys.path.extend(['/home/claude'])\n",
    # Lo stesso modulo per un'altra strada: `os.sys` è `sys`.
    "import os\nos.sys.path.insert(0, '/home/claude')\n",
    # Lo stesso modulo legato per nome, con un alias: e' questa la riga che
    # il ramo `ImportFrom` di `_nomi_del_modulo_sys` serve — senza alias il
    # nome sarebbe `sys`, che il valore di partenza ha gia'.
    "from os import sys as _s\n_s.path.insert(0, '/home/claude')\n",
    # Il bersaglio è un nome semplice: `sys` non compare nella riga.
    "from sys import path\npath.insert(0, '/home/claude')\n",
    "from sys import path as _p\n_p += ['/home/claude']\n",
    # Il letterale sta dentro una chiamata: stessa cartella, stessa riga.
    "import os, sys\n"
    "sys.path.insert(0, os.path.join('/home/claude', 'src'))\n",
    "import os, sys\nsys.path += [os.path.expanduser('/home/claude')]\n",
])
def test_il_criterio_vede_le_altre_grafie_dello_stesso_inserimento(sorgente):
    """`+=` e `extend` sono la stessa riga di `insert`, e valgono lo stesso.

    Riconoscerne una sola sarebbe il difetto di questa sezione applicato a
    sé stessa: la riga muta resterebbe, con sopra un test verde a dire che
    non c'è. Vale per tutti e tre i pezzi dell'istruzione, non solo per il
    verbo in mezzo: il bersaglio può essere un nome (`from sys import path`)
    e il letterale può stare dentro una chiamata — le due riscritture più
    ovvie della stessa riga, e le due che passavano.

    Vale anche fra i verbi, uno per uno, ed è la parte che mancava: i tre
    stanno in un criterio solo e a `append` non corrispondeva nessun caso.
    Misurato togliendolo dalla tupla: il file restava **tutto verde**, cioè
    il criterio dichiarava una grafia che nessun test poteva far diventare
    rossa — la stessa riga muta che questa sezione toglie, questa volta
    dentro la guardia. A nasconderlo erano proprio i due contrappesi
    (`cfg.path.append`, `path.append`): gli unici `append` del file, e verdi
    tutti e due comunque vada, perché a parlare lì è il bersaglio.
    """
    assert _percorsi_assoluti_in_sys_path(ast.parse(sorgente)) \
        == ['/home/claude']


def test_il_criterio_non_accusa_una_lista_che_si_chiama_path():
    """`path` è un nome comune: senza l'import non è `sys.path`.

    È il contrappeso della grafia qui sopra. Accusare ogni `path.append` che
    si incontri renderebbe rossa qualunque lista di percorsi costruita da un
    test, e una guardia rumorosa la si spegne — per questo il nome si
    raccoglie da `from sys import path` invece di darlo per scontato.
    """
    sorgente = (
        "path = []\n"
        "path.append('/home/claude')\n"
        "path += ['/opt/altro']\n"
    )

    assert _percorsi_assoluti_in_sys_path(ast.parse(sorgente)) == []


@pytest.mark.parametrize('sorgente', [
    # `from os import path` e' la grafia piu' comune che leghi quel nome, e
    # non lega la lista di `sys`.
    "from os import path\npath.insert(0, '/tmp/fuori')\n",
    "from os import path\npath.append('/Users/tizio/repo')\n",
    "from os import path as _p\n_p += ['/tmp/fuori']\n",
    "from os import path\npath = '/tmp/fuori'\n",
    # Lo stesso dall'altra parte: `import os` non fa di `os.path` la lista.
    "import os\nos.path.insert(0, '/tmp/fuori')\n",
    "import os\nos.path.extend(['/tmp/fuori'])\n",
])
def test_il_criterio_non_accusa_il_path_di_un_altro_modulo(sorgente):
    """Il nome giusto, legato dal modulo sbagliato: `os.path` non e' `sys.path`.

    I due raccoglitori chiedono all'import due cose ciascuno — **quale
    modulo** e **quale nome** — e a essere misurata era una sola: le grafie
    negative sbagliavano il nome (`from sys import argv`) oppure l'oggetto
    (`cfg`, `self`, una lista locale), nessuna sbagliava il modulo da cui il
    nome arriva. Misurato togliendo `node.module == 'sys'` da
    `_nomi_di_sys_path` e `a.name == 'sys'` da `_nomi_del_modulo_sys`: il
    file restava **tutto verde** tutte e due le volte.

    E le due righe che ne uscivano non sono di scuola. `from os import path`
    e' la grafia piu' comune che leghi quel nome in Python, e `import os` sta
    in meta' di questa suite: sotto la mutazione un `path.append(...)` o un
    `os.path.insert(...)` diventano un rosso con sopra un messaggio che parla
    di `sys.path` e cita una issue che non c'entra — la guardia rumorosa che
    questa sezione dichiara di non voler essere, per la terza volta sullo
    stesso estremo della riga.
    """
    assert _percorsi_assoluti_in_sys_path(ast.parse(sorgente)) == []


@pytest.mark.parametrize('sorgente', [
    # L'assegnazione secca: un oggetto qualunque con un campo `path`.
    "import sys\ncfg.path = '/tmp/fuori'\n",
    "import sys\nself.path = '/tmp/fuori'\n",
    # Le altre due grafie, sullo stesso attributo.
    "import sys\ncfg.path.append('/tmp/fuori')\n",
    "import sys\ncfg.path += ['/tmp/fuori']\n",
])
def test_il_criterio_non_accusa_un_campo_path_di_un_altro_oggetto(sorgente):
    """`cfg.path` non è `sys.path`, e il rosso parlerebbe di sys.path.

    È il contrappeso che il nome semplice aveva già — `_nomi_di_sys_path`
    raccoglie il nome dall'import invece di accusare ogni `path` che capiti —
    e che all'attributo mancava: bastava chiamarsi `path`, qualunque cosa ci
    stesse prima. Il principio era scritto per uno dei due estremi della riga
    e valeva per uno solo dei due.

    L'`import sys` di ogni grafia non è quello che le tiene verdi, e dirlo
    era il verde per la ragione sbagliata al contrario: `_nomi_del_modulo_sys`
    ci mette `sys` **sempre**, e lo dichiara — un file che lo usa senza
    importarlo lo prende comunque da lì — quindi togliere l'import non
    cambierebbe nessuno di questi verdetti. Resta perché è la grafia realistica
    (un file che scrive `cfg.path` di solito importa anche `sys`), non perché
    porti il verdetto. A portarlo è il bersaglio, che qui non è `sys`; il caso
    opposto — il modulo giusto, il membro sbagliato — è il test qui sotto.
    """
    assert _percorsi_assoluti_in_sys_path(ast.parse(sorgente)) == []


@pytest.mark.parametrize('sorgente', [
    # Il modulo giusto, l'attributo sbagliato.
    "import sys\nsys.argv.insert(0, '/tmp/fuori')\n",
    "import sys\nsys.argv += ['/tmp/fuori']\n",
    "import sys\nsys.executable = '/tmp/fuori'\n",
    # Lo stesso, dietro l'altro attributo: `os.sys` è `sys`.
    "import os\nos.sys.argv.insert(0, '/tmp/fuori')\n",
    # Il nome semplice: l'import da `sys` c'è, ma non lega `path`.
    "from sys import argv\nargv.insert(0, '/tmp/fuori')\n",
    "from sys import argv as _a\n_a += ['/tmp/fuori']\n",
])
def test_il_criterio_non_accusa_un_altro_membro_di_sys(sorgente):
    """`sys.argv` non è `sys.path`, e nemmeno l'`argv` legato per nome.

    L'altra metà del contrappeso qui sopra, e la metà che non era misurata.
    Il bersaglio si chiede in due pezzi — il modulo *e* il campo — e i test
    guardavano solo il primo: tutte le grafie negative sbagliavano oggetto
    (`cfg`, `self`, una lista locale), nessuna sbagliava membro. Misurato
    togliendo `nodo.attr == 'path'` da `_e_un_path`: il file restava tutto
    verde, e `sys.argv.insert(0, '/abs')` — riga che mezza suite potrebbe
    scrivere — diventava un rosso con sopra un messaggio che parla di
    `sys.path` e cita una issue che non c'entra.

    Le ultime due righe sono la stessa distrazione sul nome semplice:
    `_nomi_di_sys_path` chiede all'import di legare proprio `path`, e
    togliendo quel filtro — anche lì, file tutto verde — `from sys import
    argv` faceva di `argv` un alias di `sys.path`.

    È il terzo giro della stessa famiglia su questa sezione: il principio
    scritto per un estremo e applicato a uno solo, con la differenza che
    stavolta a essere scritto per metà non era il criterio ma il suo
    contrappeso.
    """
    assert _percorsi_assoluti_in_sys_path(ast.parse(sorgente)) == []


def test_il_criterio_non_accusa_i_percorsi_calcolati():
    """La forma che usa il resto della suite resta legittima.

    Ed è verde per la ragione giusta: non perché siano chiamate — dentro le
    chiamate ora si guarda — ma perché non contengono nessun letterale
    assoluto. È questo test a tenere il criterio largo dal diventare
    rumoroso.
    """
    sorgente = (
        "import os, sys\n"
        "sys.path.insert(0, os.path.abspath(\n"
        "    os.path.join(os.path.dirname(__file__), '../src')))\n"
        "sys.path.insert(1, os.path.join(REPO_ROOT, 'utils'))\n"
        "sys.path.insert(0, str(REPO_ROOT / 'utils'))\n"
        "sys.path += [os.path.join(REPO_ROOT, 'utils')]\n"
        "sys.path.extend([str(REPO_ROOT / 'utils')])\n"
        "sys.path[:0] = [os.path.dirname(__file__)]\n"
    )

    assert _percorsi_assoluti_in_sys_path(ast.parse(sorgente)) == []
