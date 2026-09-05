# =============================================================================
# tests/shared/test_stdout_contract.py
# =============================================================================
"""
Il contratto di stdout, in forma eseguibile (issue #178, scaglione #187).

PGE ha due canali diagnostici, e la #178 li ha separati per *destinatario*:

- **protocollo** — righe che `render_pipeline.py` di PGE-ui parsa riga per riga
  per ricavarne gli eventi NDJSON dell'editor. Restano su stdout, con quel
  formato esatto. Sono le `[CACHE] <id>: DIRTY|clean` dei renderer (da cui
  l'editor deriva `stream-start`/`stream-done`) e i path del blocco
  riassuntivo;
- **diagnostica** — righe che nessuno parsa e nessuno legge come interfaccia.
  Vanno al logger. Sono le registrazioni dinamiche di strategy: operazione da
  sviluppatore che in una pipeline di rendering normale non compare mai.

Questa suite esiste perche' la classificazione era prosa, e la prosa non si
accorge di essere stata contraddetta. Le due meta' falliscono in direzioni
opposte e vanno guardate entrambe: portare al logger una riga di protocollo
rompe l'interfaccia utente di un altro repository *senza toccare un test di
PGE* (per csound e supercollider la riga `[CACHE]` non ha oggi nessuna
asserzione di comportamento — solo questa); rimettere un `print()` in
`strategies/` riapre in silenzio la porta che la #187 ha chiuso.
"""
import ast
import os

import pytest

SRC_PGE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'pge'))

# I tre renderer che dichiarano lo stato della cache all'editor.
RENDERER_CON_PROTOCOLLO_CACHE = [
    os.path.join('rendering', 'numpy_audio_renderer.py'),
    os.path.join('rendering', 'csound_renderer.py'),
    os.path.join('rendering', 'supercollider_renderer.py'),
]


def _sorgente(relpath):
    with open(os.path.join(SRC_PGE, relpath), encoding='utf-8') as f:
        return f.read()


def _print_calls(tree):
    """Le chiamate a `print(...)` presenti nell'albero."""
    return [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == 'print'
    ]


def _testo_letterale(node):
    """Le parti costanti di un argomento, f-string comprese.

    La riga di protocollo e' una f-string: il prefisso `[CACHE] ` e' un
    `Constant` dentro una `JoinedStr`, e cercarlo come stringa intera non lo
    troverebbe.
    """
    pezzi = []
    for sotto in ast.walk(node):
        if isinstance(sotto, ast.Constant) and isinstance(sotto.value, str):
            pezzi.append(sotto.value)
    return ''.join(pezzi)


# =============================================================================
# 1. PROTOCOLLO — resta su stdout
# =============================================================================

@pytest.mark.parametrize('relpath', RENDERER_CON_PROTOCOLLO_CACHE)
def test_la_riga_cache_resta_su_stdout(relpath):
    """`[CACHE] <id>: <status>` e' protocollo: `print()`, non logger.

    E' la riga da cui `parse_render_line` ricava `stream-start` e
    `stream-done`. Spostarla al logger lascia la barra di avanzamento
    dell'editor ferma a zero per tutto il rendering.
    """
    tree = ast.parse(_sorgente(relpath))

    con_cache = [c for c in _print_calls(tree)
                 if any('[CACHE]' in _testo_letterale(a) for a in c.args)]

    assert con_cache, (
        f"{relpath}: la riga di protocollo [CACHE] non e' piu' un print(). "
        "PGE-ui la parsa da stdout: vedi issue #178."
    )


@pytest.mark.parametrize('relpath', RENDERER_CON_PROTOCOLLO_CACHE)
def test_la_riga_cache_e_flushata(relpath):
    """`flush=True`: l'editor la legge mentre il rendering e' in corso.

    Senza flush la riga resta nel buffer del sottoprocesso e arriva a fine
    rendering, quando non ha piu' niente da annunciare.
    """
    tree = ast.parse(_sorgente(relpath))

    for chiamata in _print_calls(tree):
        if not any('[CACHE]' in _testo_letterale(a) for a in chiamata.args):
            continue
        flush = [k for k in chiamata.keywords if k.arg == 'flush']
        assert flush and getattr(flush[0].value, 'value', False) is True, \
            f"{relpath}: la riga [CACHE] non e' piu' flushata"


# =============================================================================
# 2. DIAGNOSTICA — non torna su stdout
# =============================================================================

def _moduli_strategie():
    cartella = os.path.join(SRC_PGE, 'strategies')
    return sorted(f for f in os.listdir(cartella) if f.endswith('.py'))


@pytest.mark.parametrize('modulo', _moduli_strategie())
def test_le_strategie_non_stampano(modulo):
    """Nessun `print()` in `strategies/`: la registrazione e' diagnostica.

    Non e' una regola di stile. Chi registra una strategy sta estendendo il
    motore, non rendendo: la sua conferma non ha titolo per attraversare il
    canale che l'editor parsa.
    """
    tree = ast.parse(_sorgente(os.path.join('strategies', modulo)))

    assert not _print_calls(tree), (
        f"strategies/{modulo}: print() reintrodotto. La diagnostica va a "
        "`log_strategy_registration` (issue #187)."
    )
