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
PGE* (per csound e supercollider la riga `[CACHE]` non ha nessun'altra
asserzione di comportamento — solo questa); rimettere un `print()` in
`strategies/` riapre in silenzio la porta che la #187 ha chiuso.

**Chi emette la riga non e' solo un renderer.** I tre renderer la stampano
sul percorso diretto (uno stream alla volta), ma la pipeline in due stadi
passa da `Generator.write_sco_files`, che delega a
`StreamCacheManager.get_dirty_stream_dicts`: e' li' che la riga esce, per
tutti gli stream in blocco, prima che un renderer veda alcunche'. E' anche
l'emettitore piu' esposto: il suo modulo contiene *altri* `print()` che la
#178 non ha ancora classificato, quindi e' il prossimo su cui passera' un
giro di conversione al logger, e chi lo fara' avra' sotto gli occhi righe
`[CACHE]` di due nature diverse. Percio' sta nella lista come gli altri.

**Il criterio e' la forma, non il prefisso.** `[CACHE]` da solo non
discrimina: lo stesso modulo stampa anche `[CACHE] <n>/<m> stream da
ricompilare`, che PGE-ui non parsa (la sua regex vuole `<token-senza-spazi>:`
subito dopo il prefisso). Cercare la sottostringa avrebbe lasciato passare la
scomparsa della riga vera. Le chiamate sono quindi ricomposte in un
*template* — ogni `{...}` di una f-string diventa `{}` — e cio' che la
guardia pretende e' `[CACHE] {}: `, la forma esatta che quella regex
riconosce.
"""
import ast
import os

import pytest

SRC_PGE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'pge'))

# I moduli che dichiarano all'editor lo stato della cache, stream per stream.
# I tre renderer sul percorso diretto; il cache manager sul percorso in due
# stadi (`Generator.write_sco_files` -> `get_dirty_stream_dicts`), dove la riga
# esce prima che un renderer esista.
MODULI_CON_PROTOCOLLO_CACHE = [
    os.path.join('rendering', 'numpy_audio_renderer.py'),
    os.path.join('rendering', 'csound_renderer.py'),
    os.path.join('rendering', 'supercollider_renderer.py'),
    os.path.join('rendering', 'stream_cache_manager.py'),
]

# La forma che `_RE_CACHE_LINE` di PGE-ui riconosce: prefisso, un token senza
# spazi, i due punti. Il resto della riga non e' vincolato.
PREFISSO_PROTOCOLLO_CACHE = '[CACHE] {}: '


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


def _template(node):
    """Il testo di un argomento con ogni interpolazione ridotta a `{}`.

    La riga di protocollo e' una f-string: il prefisso `[CACHE] ` e' un
    `Constant` dentro una `JoinedStr`, e cercarlo come stringa intera non lo
    troverebbe. Ma raccogliere le costanti con `ast.walk` non basta: l'ordine
    di visita non e' quello della riga, e le costanti annidate dentro
    un'interpolazione (`{'DIRTY' if dirty else 'clean'}`, in supercollider)
    finirebbero nel testo come se fossero letterali. Qui si cammina invece
    `JoinedStr.values` in ordine, e ogni `FormattedValue` diventa `{}` senza
    che se ne guardi dentro: quel che resta e' la *forma* della riga, ed e'
    esattamente cio' su cui la regex di PGE-ui decide.
    """
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else ''
    if isinstance(node, ast.JoinedStr):
        return ''.join(
            pezzo.value if isinstance(pezzo, ast.Constant)
            and isinstance(pezzo.value, str)
            else '{}'
            for pezzo in node.values
        )
    return ''


def _print_di_protocollo(tree):
    """Le `print()` la cui forma e' quella che PGE-ui parsa come stream."""
    return [
        c for c in _print_calls(tree)
        if any(_template(a).startswith(PREFISSO_PROTOCOLLO_CACHE)
               for a in c.args)
    ]


# =============================================================================
# 1. PROTOCOLLO — resta su stdout
# =============================================================================

@pytest.mark.parametrize('relpath', MODULI_CON_PROTOCOLLO_CACHE)
def test_la_riga_cache_resta_su_stdout(relpath):
    """`[CACHE] <id>: <status>` e' protocollo: `print()`, non logger.

    E' la riga da cui `parse_render_line` ricava `stream-start` e
    `stream-done`. Spostarla al logger lascia la barra di avanzamento
    dell'editor ferma a zero per tutto il rendering.
    """
    tree = ast.parse(_sorgente(relpath))

    assert _print_di_protocollo(tree), (
        f"{relpath}: la riga di protocollo `{PREFISSO_PROTOCOLLO_CACHE}...` "
        "non e' piu' un print() con quella forma. PGE-ui la parsa da stdout "
        "per ricavarne stream-start/stream-done: vedi issue #178."
    )


@pytest.mark.parametrize('relpath', MODULI_CON_PROTOCOLLO_CACHE)
def test_la_riga_cache_e_flushata(relpath):
    """`flush=True`: l'editor la legge mentre il rendering e' in corso.

    Senza flush la riga resta nel buffer del sottoprocesso e arriva a fine
    rendering, quando non ha piu' niente da annunciare.
    """
    tree = ast.parse(_sorgente(relpath))

    for chiamata in _print_di_protocollo(tree):
        flush = [k for k in chiamata.keywords if k.arg == 'flush']
        assert flush and getattr(flush[0].value, 'value', False) is True, \
            f"{relpath}: la riga [CACHE] non e' piu' flushata"


# =============================================================================
# 1b. IL CRITERIO DISCRIMINA — altrimenti la guardia e' verde a vuoto
# =============================================================================
# Una guardia che cerca la sottostringa `[CACHE]` non si accorge della
# sparizione della riga vera finche' nel modulo resta una qualunque altra riga
# che comincia per `[CACHE]` — e in `stream_cache_manager.py` ce n'e' una
# (`[CACHE] <n>/<m> stream da ricompilare`, che PGE-ui non parsa). Questi due
# test misurano il criterio sui casi reali, cosi' che a indebolirlo qualcosa
# suoni.

def test_il_criterio_riconosce_la_riga_per_stream():
    """La forma per stream, in tutte le grafie che i moduli usano davvero."""
    sorgente = (
        'print(f"[CACHE] {stream.stream_id}: {status}", flush=True)\n'
        'print(f"[CACHE] {sid}: {\'DIRTY\' if dirty else \'clean\'}",'
        ' flush=True)\n'
    )

    assert len(_print_di_protocollo(ast.parse(sorgente))) == 2


def test_il_criterio_scarta_le_righe_cache_che_nessuno_parsa():
    """`[CACHE]` come prefisso non basta: serve `<token-senza-spazi>:`.

    Sono le righe che la regex di PGE-ui lascia cadere. Contarle come
    protocollo renderebbe la guardia verde anche dopo aver spostato al logger
    l'unica riga che l'editor legge davvero.
    """
    sorgente = (
        'print(f"[CACHE] {len(dirty)}/{len(tutti)} stream da ricompilare",'
        ' flush=True)\n'
        'print(f"[CACHE] Stream da scrivere: {ids}", flush=True)\n'
        'print("[CACHE] qualcosa di generico", flush=True)\n'
    )

    assert _print_di_protocollo(ast.parse(sorgente)) == []


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
