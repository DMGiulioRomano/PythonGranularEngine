# =============================================================================
# tests/test_cli_builtin_handlers.py
# =============================================================================
"""
Guardia strutturale sugli `except` di `pge.cli` (issue #257).

La #241 aveva spostato l'handler `FileNotFoundError` dal fondo del `try` di
`main()` alle due righe che caricano lo YAML. La correzione funzionava, ma la
garanzia che rivendicava — «qui puo' fallire solo il file di configurazione» —
era vera per *estensione fisica del blocco*, non per il tipo dell'eccezione:
una riga in piu' dentro quel `try` (un `!include`, una prescansione dei
sample, il passaggio ad `api.load_generator`, che impacchetta anche
`create_elements`) rimetteva in circolo il messaggio falso senza che niente
diventasse rosso.

La #257 ha tolto la premessa invece di puntellarla: i guasti del caricamento
hanno un tipo di dominio (`ConfigFileNotFoundError`, `ConfigParseError`) e la
CLI non intercetta piu' nessun builtin lungo la pipeline. Questo file e' la
forma eseguibile di quella regola, letta dal sorgente come AST invece che
riasserita a parole.

Due guardie, di raggio diverso:

1. **Nessun handler di `cli.py` cattura un errore della famiglia `OSError`.**
   E' la famiglia che risale da qualunque profondita' di I/O — csound assente
   (#241), un sample illeggibile, un disco pieno — e per questo l'unica che il
   tipo, da solo, non basta a collocare. Una `except FileNotFoundError` che
   tornasse in questo file avrebbe di nuovo bisogno di stare *nel punto
   giusto* per non mentire.
2. **Il `try` che avvolge la pipeline non contiene nessun handler su un
   builtin**, a nessuna profondita', e i suoi due rami sono `EngineError` e
   il generico. Gli `except ValueError` sopravvissuti in `main()` stanno
   attorno a `int()`/`float()` su `sys.argv` e non toccano la pipeline: la
   guardia li lascia stare di proposito, ed e' il motivo per cui e' scritta
   sul blocco e non sull'intera funzione.

Entrambe passano da `_colpevole`, e la ragione e' un `except:` senza tipo:
non nomina nessun builtin, quindi due guardie lette sui soli nomi
resterebbero verdi proprio sull'handler piu' largo che esista — che cattura
la famiglia OSError e per giunta `EngineError`, cioe' rimette in circolo il
messaggio falso passando da tutte e due. Una guardia che dipende da come
l'handler e' scritto ripete, un piano piu' su, il difetto che la #257
corregge nel codice.
"""

# Le annotazioni di questo file usano PEP 604 (`str | None`), che sulla 3.9
# -- il minimo di `requires-python`, e un job della matrice CI -- si valuta
# alla `def` e alza TypeError: il file moriva in raccolta, cioe' la guardia
# non falliva, spariva. Il future import le rende stringhe.
from __future__ import annotations

import ast
import builtins
import os

import pytest


CLI_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'src', 'pge', 'cli.py')


@pytest.fixture(scope='module')
def albero():
    with open(CLI_PATH, encoding='utf-8') as f:
        return ast.parse(f.read(), filename=CLI_PATH)


def _nomi_catturati(handler: ast.ExceptHandler) -> list[str]:
    """I nomi (dotted o semplici) che un `except` intercetta."""
    if handler.type is None:
        return []
    tipi = (handler.type.elts
            if isinstance(handler.type, ast.Tuple) else [handler.type])
    nomi = []
    for t in tipi:
        if isinstance(t, ast.Name):
            nomi.append(t.id)
        elif isinstance(t, ast.Attribute):
            nomi.append(t.attr)
    return nomi


def _colpevole(handler: ast.ExceptHandler, famiglia=None) -> str | None:
    """Perche' questo `except` viola la regola, o None se non la viola.

    `famiglia` restringe ai builtin che ereditano da quel tipo; None
    significa «qualunque builtin».

    Un `except:` senza tipo e' colpevole in entrambe le letture, e va detto
    qui e non in ognuna delle due guardie: non nomina niente, quindi una
    guardia scritta sui soli nomi lo lascerebbe passare — restando verde
    proprio sull'handler piu' largo che esista, che cattura tutta la
    famiglia OSError e anche `EngineError`. E' la stessa distinzione che
    questa issue corregge nel codice: la garanzia non puo' dipendere da come
    l'handler e' scritto.
    """
    if handler.type is None:
        return 'except: nudo (cattura tutto, famiglia OSError compresa)'
    for nome in _nomi_catturati(handler):
        cls = _builtin_exception(nome)
        if cls is not None and (famiglia is None or issubclass(cls, famiglia)):
            return nome
    return None


def _builtin_exception(nome: str):
    """La classe builtin omonima, se e' un'eccezione; altrimenti None.

    Derivata da `builtins`, non da un elenco trascritto: un elenco andrebbe
    aggiornato da chi aggiunge l'handler, cioe' proprio da chi non ci pensa.
    """
    cls = getattr(builtins, nome, None)
    if isinstance(cls, type) and issubclass(cls, BaseException):
        return cls
    return None


def _funzione(albero, nome):
    for nodo in ast.walk(albero):
        if isinstance(nodo, ast.FunctionDef) and nodo.name == nome:
            return nodo
    raise AssertionError(f"funzione {nome!r} non trovata in {CLI_PATH}")


def _try_della_pipeline(main_node):
    """Il `try` che avvolge caricamento, generazione e render.

    Individuato dal suo contenuto (`generator.load_yaml()`), non dalla sua
    posizione nel file: e' la stessa differenza che questa issue ha corretto
    nel codice.
    """
    candidati = [
        nodo for nodo in ast.walk(main_node)
        if isinstance(nodo, ast.Try)
        and any(isinstance(c, ast.Call)
                and isinstance(c.func, ast.Attribute)
                and c.func.attr == 'load_yaml'
                for c in ast.walk(nodo))
    ]
    assert candidati, "nessun try contiene la chiamata a load_yaml()"
    # Il piu' esterno: quello i cui handler chiudono la pipeline.
    return max(candidati, key=lambda n: len(list(ast.walk(n))))


def _dentro_al_blocco(blocco):
    """Le istruzioni che stanno *dentro* il `try`, a qualunque ramo.

    `body` piu' `orelse` e `finalbody`: la regola di questo modulo dice «a
    nessuna profondita'», e leggere il solo `body` la lasciava piu' stretta
    di come e' scritta -- un handler messo in un `finally:` (o in un `else:`)
    e' dentro il blocco quanto uno messo nel corpo, e per la famiglia OSError
    sarebbe stato colto solo dall'altra guardia, quella su tutto il file.

    `handlers` no, ed e' l'unica esclusione: li' i due rami sono `EngineError`
    e `Exception`, cioe' un builtin per costruzione, e li fissa
    test_la_pipeline_ha_i_due_rami_dichiarati. Includerli renderebbe questa
    guardia rossa sul codice sano.
    """
    return list(blocco.body) + list(blocco.orelse) + list(blocco.finalbody)


def test_cli_non_cattura_nessun_errore_della_famiglia_oserror(albero):
    colpevoli = []
    for nodo in ast.walk(albero):
        if not isinstance(nodo, ast.ExceptHandler):
            continue
        motivo = _colpevole(nodo, famiglia=OSError)
        if motivo is not None:
            colpevoli.append((motivo, nodo.lineno))
    assert not colpevoli, (
        "pge/cli.py cattura di nuovo un errore della famiglia OSError: "
        f"{colpevoli}. Un guasto di I/O risale da qualunque profondita', "
        "quindi il tipo non basta a collocarlo e il messaggio torna a "
        "dipendere da dove sta l'handler (issue #241/#257). Dagli un tipo "
        "di dominio nel punto che lo produce, come "
        "ConfigFileNotFoundError."
    )


def test_la_pipeline_non_contiene_handler_su_builtin(albero):
    blocco = _try_della_pipeline(_funzione(albero, 'main'))
    colpevoli = []
    for corpo in _dentro_al_blocco(blocco):
        for nodo in ast.walk(corpo):
            if not isinstance(nodo, ast.ExceptHandler):
                continue
            motivo = _colpevole(nodo)
            if motivo is not None:
                colpevoli.append((motivo, nodo.lineno))
    assert not colpevoli, (
        "un handler su un tipo builtin e' tornato dentro il try della "
        f"pipeline: {colpevoli}. Il messaggio che ne esce vale finche' "
        "il blocco non cresce, e cresce senza che nessun test lo dica "
        "(issue #257)."
    )


def test_la_pipeline_ha_i_due_rami_dichiarati(albero):
    """`EngineError` prima, il generico dopo: l'ordine e' il contratto.

    Se un domani `ConfigFileNotFoundError` — che eredita `FileNotFoundError`
    — passasse da un ramo builtin messo davanti, il tipo di dominio
    smetterebbe di servire a chi lo cattura, che e' l'unica cosa a cui serve.
    """
    blocco = _try_della_pipeline(_funzione(albero, 'main'))
    catturati = [_nomi_catturati(h) for h in blocco.handlers]
    assert catturati == [['EngineError'], ['Exception']], catturati


# La forma che le due guardie non vedrebbero, se leggessero i soli nomi. Sta
# qui come sorgente e non come sabotaggio di `cli.py`: e' l'unico modo di
# misurare una guardia senza rompere il file che sorveglia.
SABOTAGGIO = """
def main():
    try:
        generator.load_yaml()
        try:
            api.render(generator)
        except:
            print("Errore: file non trovato")
            sys.exit(1)
    except EngineError:
        pass
    except Exception:
        pass
"""


def test_la_guardia_vede_un_except_nudo():
    """La guardia misurata invece che riasserita.

    `except:` non compare in nessun elenco di nomi builtin — e' proprio la
    sua assenza di tipo a renderlo la falla: cattura tutto, `EngineError`
    compreso, quindi il messaggio falso della #241 rientrerebbe da li' con i
    tre test di questo file verdi. Il sabotaggio gira su un albero sintetico
    con la stessa forma di `main()`.
    """
    albero = ast.parse(SABOTAGGIO)
    blocco = _try_della_pipeline(_funzione(albero, 'main'))

    nudi = [nodo.lineno for corpo in blocco.body for nodo in ast.walk(corpo)
            if isinstance(nodo, ast.ExceptHandler) and _colpevole(nodo)]
    assert nudi, "la guardia sulla pipeline non vede un `except:` nudo"

    famiglia = [nodo.lineno for nodo in ast.walk(albero)
                if isinstance(nodo, ast.ExceptHandler)
                and _colpevole(nodo, famiglia=OSError)]
    assert famiglia, "la guardia sulla famiglia OSError non vede un `except:` nudo"


def test_la_guardia_vede_un_handler_nel_finally():
    """La misura dell'unica esclusione che `_dentro_al_blocco` non fa.

    Leggendo il solo `body`, un `except FileNotFoundError` messo in un
    `finally:` (o in un `else:`) del `try` della pipeline restava invisibile a
    questa guardia: la regola dice «a nessuna profondita'», e valeva a una
    profondita' sola. Per la famiglia OSError lo avrebbe colto l'altra
    guardia, quella su tutto il file; per ogni altro builtin, nessuna.
    """
    albero = ast.parse(
        "def main():\n"
        "    try:\n"
        "        generator.load_yaml()\n"
        "    except EngineError:\n"
        "        sys.exit(1)\n"
        "    except Exception:\n"
        "        sys.exit(1)\n"
        "    finally:\n"
        "        try:\n"
        "            cleanup()\n"
        "        except KeyError:\n"
        "            pass\n"
    )
    blocco = _try_della_pipeline(_funzione(albero, 'main'))
    visti = [_colpevole(n) for corpo in _dentro_al_blocco(blocco)
             for n in ast.walk(corpo) if isinstance(n, ast.ExceptHandler)]
    assert visti == ['KeyError'], visti
    # E l'esclusione resta: i due rami del blocco non sono colpevoli di se'
    # stessi, o la guardia sarebbe rossa su ogni CLI sana.
    assert _colpevole(blocco.handlers[1]) == 'Exception'
    assert blocco.handlers[1] not in [
        n for corpo in _dentro_al_blocco(blocco) for n in ast.walk(corpo)]


def test_la_guardia_lascia_stare_gli_handler_legittimi():
    """L'altra meta': una guardia che dice sempre di si' e' muta quanto una
    che dice sempre di no. `EngineError` e le sue sorelle di dominio non sono
    builtin, e un `except ValueError` attorno a un `int()` di `sys.argv` non
    e' nella pipeline — sono i due casi che devono restare verdi."""
    albero = ast.parse(
        "def main():\n"
        "    try:\n"
        "        n = int(sys.argv[1])\n"
        "    except ValueError:\n"
        "        sys.exit(1)\n"
        "    try:\n"
        "        generator.load_yaml()\n"
        "    except EngineError:\n"
        "        sys.exit(1)\n"
    )
    handlers = [n for n in ast.walk(albero) if isinstance(n, ast.ExceptHandler)]
    assert [_colpevole(h, famiglia=OSError) for h in handlers] == [None, None]

    blocco = _try_della_pipeline(_funzione(albero, 'main'))
    dentro = [n for corpo in _dentro_al_blocco(blocco) for n in ast.walk(corpo)
              if isinstance(n, ast.ExceptHandler)]
    assert dentro == [], "il try della pipeline non contiene handler propri"
