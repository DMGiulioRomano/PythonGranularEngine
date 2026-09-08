# =============================================================================
# tests/test_minimum_python_syntax.py
# =============================================================================
"""
Il sorgente resta leggibile dal Python piu' vecchio che `pyproject.toml`
dichiara di supportare: la grammatica, e le annotazioni che si valutano a
runtime.

Il repo dichiara `requires-python = ">=3.9"` e la matrice CI ci gira sopra,
ma **nessuno sviluppa su 3.9**: in locale si lavora sull'interprete corrente,
dove `str | None` in una firma e' legale, e il rosso arriva solo dal job piu'
vecchio della matrice -- un'ora dopo, su una PR che in locale era verde.

E' successo davvero, dentro la #257: `tests/test_cli_builtin_handlers.py`
-- cioe' proprio la guardia che tiene in piedi la regola della issue --
dichiarava `-> str | None` senza `from __future__ import annotations`, e su
3.9 esplodeva in raccolta con un `TypeError`. Il file non veniva importato
affatto: la guardia non falliva, semplicemente non esisteva piu'.

Che cosa si valuta e quando, perche' la guardia non e' piu' larga del vero:

- le annotazioni di **firma** (parametri e ritorno) si valutano alla `def`;
- le annotazioni di **modulo e di classe** (`x: T = ...`) si valutano
  all'esecuzione del corpo;
- quelle **locali dentro una funzione** non si valutano mai;
- `from __future__ import annotations` le rende tutte stringhe, quindi un
  file che ce l'ha e' fuori discussione.

Solo PEP 604 (`X | Y`) e' un problema: PEP 585 (`list[str]`, `dict[str, int]`)
funziona gia' dalla 3.9.

Un limite dichiarato, e va detto perche' non e' una dimenticanza: questa meta'
guarda le **annotazioni**, non ogni `|` che l'import valuta. Un alias di tipo
scritto come assegnamento -- `Numero = int | None` a livello di modulo -- muore
sulla 3.9 nello stesso identico modo, e nessuna delle due meta' lo vede: e'
sintatticamente valido, quindi il parser non protesta, e non e' un'annotazione,
quindi non passa di qui. Allargare la lettura a ogni `Assign` non e' la
risposta: `MASK = READ | WRITE` e' un or bit a bit legittimo, e una guardia che
lo accusasse chiederebbe di riscrivere codice sano -- il difetto che l'altra
meta' evita per costruzione facendo la domanda al parser. Se un alias del genere
dovesse comparire, il posto dove restringere e' il caso `X | None`, l'unico in
cui un or bit a bit non ha mai senso.

Quella meta' pero' non basta, perche' il sintomo che questo file commemora ha
due cause e non una. Un'annotazione PEP 604 muore alla `def`; una `match`, un
`except*`, un `type X = int`, una f-string annidata muoiono un momento prima,
alla compilazione -- e l'esito e' lo stesso identico: il file non viene
importato, il test che conteneva sparisce invece di fallire, e il rosso arriva
solo dal job piu' vecchio della matrice. Cercare la sola PEP 604 avrebbe
lasciato fuori la classe piu' numerosa (tutta la sintassi nuova dalla 3.10 in
poi) proprio mentre dichiarava di sorvegliare il minimo. La seconda meta' non
si scrive a mano: `ast.parse(..., feature_version=minimo)` chiede al parser di
casa, ed e' il parser a dire di no.

La soglia non e' trascritta qui: si legge da `requires-python`. Il giorno in
cui il minimo passa a 3.10 la meta' su PEP 604 si spegne da sola; la meta'
sulla grammatica no -- si limita ad alzare l'asticella con lui.
"""

import ast
import os
import re

import pytest


RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARTELLE = ('src', 'tests', 'utils')


def _minimo_dichiarato():
    """`(major, minor)` da `requires-python` di pyproject.toml, o None.

    Letto a mano invece che con tomllib: quello arriva in 3.11, e un test
    sulla compatibilita' con la 3.9 che non gira sulla 3.9 sarebbe una barzelletta.
    """
    percorso = os.path.join(RADICE, 'pyproject.toml')
    with open(percorso, encoding='utf-8') as f:
        testo = f.read()
    m = re.search(r'^\s*requires-python\s*=\s*["\'][^0-9]*(\d+)\.(\d+)',
                  testo, re.MULTILINE)
    return (int(m.group(1)), int(m.group(2))) if m else None


def _sorgenti():
    for cartella in CARTELLE:
        base = os.path.join(RADICE, cartella)
        for r, dirs, fs in os.walk(base):
            dirs[:] = [d for d in dirs if d not in ('__pycache__', '.venv')]
            for fn in fs:
                if fn.endswith('.py'):
                    yield os.path.join(r, fn)


def _annotazioni_valutate(albero):
    """Le annotazioni che l'interprete valuta davvero, con la loro riga.

    Firme di funzione ovunque; `AnnAssign` solo fuori dai corpi di funzione,
    dove non si valutano. La discesa e' esplicita proprio per poter smettere
    all'ingresso di una funzione: `ast.walk` non distingue i due casi.

    Una `class` riapre la discesa, e non e' un dettaglio: il suo corpo si
    esegue quando si esegue la `class`, quindi le sue annotazioni si valutano
    anche quando la classe e' dichiarata dentro una funzione. Portandosi
    dietro il flag della funzione ospite, la guardia le classificava come
    locali -- cioe' taceva sull'unico caso in cui «dentro una funzione» e
    «non valutata» non coincidono, che e' esattamente la distinzione che la
    docstring del modulo tiene separata.
    """
    fuori = []

    def scendi(nodo, dentro_funzione):
        for figlio in ast.iter_child_nodes(nodo):
            if isinstance(figlio, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = figlio.args
                for a in (list(args.posonlyargs) + list(args.args)
                          + list(args.kwonlyargs)
                          + [args.vararg, args.kwarg]):
                    if a is not None and a.annotation is not None:
                        fuori.append((a.annotation, figlio.lineno))
                if figlio.returns is not None:
                    fuori.append((figlio.returns, figlio.lineno))
                scendi(figlio, True)
            elif isinstance(figlio, ast.ClassDef):
                scendi(figlio, False)
            elif isinstance(figlio, ast.AnnAssign):
                if not dentro_funzione and figlio.annotation is not None:
                    fuori.append((figlio.annotation, figlio.lineno))
                scendi(figlio, dentro_funzione)
            else:
                scendi(figlio, dentro_funzione)

    scendi(albero, False)
    return fuori


def _pep604(percorso):
    """Le righe del file con una `X | Y` valutata a runtime. Lista vuota se
    il file ha il future import (li' non si valuta niente).

    «Valutata a runtime» qui vuol dire *dentro un'annotazione*: un alias
    scritto come assegnamento (`Numero = int | None`) non passa da qui, per la
    ragione spiegata nella docstring del modulo.
    """
    with open(percorso, encoding='utf-8') as f:
        sorgente = f.read()
    albero = ast.parse(sorgente, filename=percorso)
    for nodo in albero.body:
        if (isinstance(nodo, ast.ImportFrom) and nodo.module == '__future__'
                and any(a.name == 'annotations' for a in nodo.names)):
            return []
    righe = []
    for annotazione, riga in _annotazioni_valutate(albero):
        for sub in ast.walk(annotazione):
            if isinstance(sub, ast.BinOp) and isinstance(sub.op, ast.BitOr):
                righe.append(riga)
                break
    return sorted(set(righe))


def _grammatica_troppo_nuova(percorso, minimo):
    """Il messaggio del parser se il file usa grammatica piu' recente di
    `minimo`, altrimenti None.

    Non c'e' un elenco di costrutti da tenere aggiornato: `feature_version`
    fa porre la domanda al parser di casa, che la sintassi delle versioni la
    conosce per mestiere. Il criterio e' la compilazione, cioe' esattamente
    il momento in cui il job piu' vecchio della matrice si accorgerebbe del
    problema -- perdendo il file intero, non un test.

    Un limite dichiarato: `feature_version` non puo' superare l'interprete
    che gira. Se un domani `requires-python` salisse sopra la versione usata
    in locale, qui la guardia direbbe soltanto «compila su questo
    interprete». E' meno di quel che promette, mai piu': non produce rossi
    falsi, e in CI il job del minimo la riporta al valore pieno.
    """
    with open(percorso, encoding='utf-8') as f:
        sorgente = f.read()
    try:
        ast.parse(sorgente, filename=percorso, feature_version=minimo)
    except SyntaxError as err:
        return err.msg
    return None


def test_requires_python_e_leggibile():
    """Senza la soglia la guardia non saprebbe quando tacere: e se
    `requires-python` sparisse, tacerebbe per sempre senza dirlo."""
    assert _minimo_dichiarato() is not None, (
        "requires-python non si legge da pyproject.toml: la soglia di questa "
        "guardia viene da li' e non e' trascritta altrove")


def test_nessuna_pep604_valutata_sotto_il_minimo_dichiarato():
    minimo = _minimo_dichiarato()
    if minimo >= (3, 10):
        pytest.skip(f"requires-python e' {minimo[0]}.{minimo[1]}: PEP 604 "
                    "e' legale ovunque, la guardia non ha piu' oggetto")

    colpevoli = []
    for percorso in sorted(_sorgenti()):
        for riga in _pep604(percorso):
            colpevoli.append(f"{os.path.relpath(percorso, RADICE)}:{riga}")

    assert not colpevoli, (
        f"annotazione PEP 604 (`X | Y`) valutata a runtime su Python "
        f"{minimo[0]}.{minimo[1]}, che pyproject.toml dichiara di supportare "
        f"e la matrice CI esegue: {colpevoli}. In locale non si vede -- "
        "l'interprete corrente la accetta -- e il job piu' vecchio muore in "
        "raccolta, quindi il file non viene importato affatto. Rimedio: "
        "`from __future__ import annotations` in testa al file, oppure "
        "`Optional[...]` / `Union[...]`."
    )


def test_la_guardia_vede_le_due_forme_valutate_e_non_la_terza():
    """La guardia misurata, non riasserita: due sorgenti sintetici, uno con
    le annotazioni che l'interprete valuta e uno con quelle che non valuta.

    La terza forma -- l'annotazione locale dentro una funzione -- e' legale
    anche su 3.9, e una guardia che la accusasse chiederebbe di cambiare
    codice che non e' rotto."""
    import tempfile

    valutate = (
        "def f(x: int | None) -> str | None: ...\n"
        "class C:\n"
        "    y: int | None = None\n"
        "z: str | None = None\n"
    )
    non_valutate = (
        "from __future__ import annotations\n"
        "def g(x: int | None) -> str | None: ...\n"
    )
    locale_soltanto = (
        "def h():\n"
        "    v: int | None = None\n"
        "    return v\n"
        "def i(x: list[str]) -> dict[str, int]: ...\n"
    )
    # Il corpo di una classe si esegue quando si esegue la `class`, anche se
    # la `class` sta dentro una funzione: quell'annotazione si valuta come
    # quella di una classe di modulo, e la riga che la ospita e' esattamente
    # la stessa. Sta qui perche' e' l'unico caso in cui «dentro una funzione»
    # e «non valutata» non coincidono, cioe' l'unico in cui la guardia puo'
    # confondere le due regole che la sua docstring tiene separate.
    classe_dentro_funzione = (
        "def j():\n"
        "    class C:\n"
        "        y: int | None = None\n"
        "    return C\n"
    )

    with tempfile.TemporaryDirectory() as d:
        for nome, sorgente, atteso in (
                ('valutate.py', valutate, 3),
                ('future.py', non_valutate, 0),
                ('locale.py', locale_soltanto, 0),
                ('classe_annidata.py', classe_dentro_funzione, 1)):
            p = os.path.join(d, nome)
            with open(p, 'w', encoding='utf-8') as f:
                f.write(sorgente)
            assert len(_pep604(p)) == atteso, (nome, _pep604(p))


def test_nessuna_grammatica_oltre_il_minimo_dichiarato():
    """L'altra meta' del sintomo, e la piu' numerosa.

    Una PEP 604 in una firma muore alla `def`; `match`, `except*`,
    `type X = int` muoiono alla compilazione. Il file non viene importato in
    entrambi i casi, quindi la guardia che conteneva sparisce invece di
    fallire: e' la stessa forma di guasto, un momento prima.
    """
    minimo = _minimo_dichiarato()
    colpevoli = []
    for percorso in sorted(_sorgenti()):
        motivo = _grammatica_troppo_nuova(percorso, minimo)
        if motivo is not None:
            colpevoli.append(f"{os.path.relpath(percorso, RADICE)}: {motivo}")

    assert not colpevoli, (
        f"sintassi non compilabile su Python {minimo[0]}.{minimo[1]}, che "
        "pyproject.toml dichiara di supportare e la matrice CI esegue: "
        f"{colpevoli}. Sull'interprete corrente non si vede, e il job piu' "
        "vecchio muore in compilazione: il file non viene importato affatto, "
        "quindi i suoi test spariscono invece di fallire. Rimedio: la stessa "
        "cosa scritta in una forma che la versione minima conosce, oppure "
        "alzare `requires-python`."
    )


def test_la_guardia_sulla_grammatica_vede_il_costrutto_nuovo():
    """La guardia misurata, non riasserita: due sorgenti sintetici e una
    soglia fissa.

    La soglia qui e' `(3, 9)` scritta a mano, e non `_minimo_dichiarato()`:
    questo test misura il meccanismo, non il minimo del repo -- servono un
    costrutto che quella soglia non conosce e uno che conosce, e la coppia
    resta significativa anche il giorno in cui `requires-python` sale.
    `match` e' il caso piu' probabile, il gradino subito sopra. La coppia
    dice le due cose che servono: che il costrutto nuovo viene visto, e che
    uno gia' valido non viene accusato -- una guardia che dicesse sempre di
    si' costringerebbe a riscrivere codice che non e' rotto.
    """
    import tempfile

    troppo_nuovo = (
        "def f(x):\n"
        "    match x:\n"
        "        case 1:\n"
        "            return 'uno'\n"
        "    return None\n"
    )
    gia_valido = (
        "from typing import Optional\n"
        "def g(x: Optional[int]) -> Optional[str]:\n"
        "    return None if x is None else str(x)\n"
    )

    with tempfile.TemporaryDirectory() as d:
        for nome, sorgente, atteso in (('nuovo.py', troppo_nuovo, True),
                                       ('vecchio.py', gia_valido, False)):
            p = os.path.join(d, nome)
            with open(p, 'w', encoding='utf-8') as f:
                f.write(sorgente)
            visto = _grammatica_troppo_nuova(p, (3, 9)) is not None
            assert visto is atteso, (nome, _grammatica_troppo_nuova(p, (3, 9)))
