# =============================================================================
# tests/shared/test_stdout_contract.py
# =============================================================================
r"""
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
sul percorso diretto, uno stream alla volta; il quarto emettitore e'
`StreamCacheManager.get_dirty_stream_dicts`, che la stampa per tutti gli
stream in blocco prima che un renderer esista.

Quel quarto pero' e' **irraggiungibile**, e la #178 l'ha accertato: il suo
unico chiamante e' `Generator.generate_score_files_per_stream`, che di
chiamanti non ne ha (`tests/test_api_stdout.py` elenca entrambi fra gli
irraggiungibili). Sta nella lista lo stesso, e la ragione e' quella per cui
la lista esiste: la riga ha la forma del protocollo, quindi il giorno che
qualcuno ricollega quel percorso arriva al parser dell'editor senza che
nessuno debba deciderlo di nuovo. Il prezzo di tenercelo e' nullo; quello di
toglierlo si paga una volta sola, tardi.

Il metodo di `Generator` si chiama cosi': la prosa di questo file diceva
`write_sco_files`, che non esiste in `src/pge/` e non e' mai esistito.

**E i punti di registrazione non stanno tutti in `strategies/`.** Sono sette,
e il settimo — `register_window_strategy` — vive in
`controllers/window_selection_strategy.py`, dove vive il registry delle
finestre. Una guardia scoped per *cartella* ne copre sei e tace sul settimo:
la `print()` che la #187 ha tolto poteva rientrare da li' lasciando verde la
suite intera. Anche questa lista e' quindi dichiarata *e* derivata, come
quella degli emettitori.

**Il criterio e' la forma, non il prefisso.** `[CACHE]` da solo non
discrimina: lo stesso modulo stampa anche `[CACHE] <n>/<m> stream da
ricompilare`, che PGE-ui non parsa (la sua regex vuole `<token-senza-spazi>:`
subito dopo il prefisso). Cercare la sottostringa avrebbe lasciato passare la
scomparsa della riga vera. Le chiamate sono quindi ricomposte in un
*template* — ogni `{...}` di una f-string diventa `{}` — e cio' che la
guardia pretende e' `[CACHE] {}: `.

**Quel template e' piu' stretto della regex di PGE-ui, di proposito.**
`_RE_CACHE_LINE` e' `^\[CACHE\]\s+(\S+):\s+(.+)$`, e un token *letterale*
la soddisfa quanto un id interpolato: `cli.py` stampa `[CACHE] Manifest:
<path>` e `[CACHE] GC: rimossi N stream orfani: [...]`, e l'editor le matcha
entrambe — a scartarle e' l'insieme degli id che la richiesta dichiara, non la
loro forma (`render_pipeline.py` lo dice in prima persona: "non tutte le righe
`[CACHE]` sono stream, e la forma non le distingue"). Il `{}` obbligatorio in
prima posizione e' quindi il criterio di *questa* guardia — che difende la riga
per stream — e non la definizione di cosa il parser a valle legge. Vedi
`docs/explanation/contratto-stdout.md`.
"""
import ast
import os
import re
import sys
from unittest.mock import patch

import pytest

from tests.main_mocks import mocks  # noqa: F401  (fixture pytest)

SRC_PGE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'pge'))

# I moduli che dichiarano all'editor lo stato della cache, stream per stream.
# I tre renderer sul percorso diretto; il cache manager dentro
# `get_dirty_stream_dicts`, che oggi nessuno raggiunge (vedi il docstring) ma
# la cui riga ha la forma del protocollo.
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
# 1a. LA LISTA E' COMPLETA — altrimenti la guardia non copre chi arriva dopo
# =============================================================================

def _moduli_pge():
    """Tutti i moduli sotto `src/pge/`, path relativo a `SRC_PGE`."""
    for radice, cartelle, files in os.walk(SRC_PGE):
        cartelle[:] = [c for c in cartelle if c != '__pycache__']
        for nome in files:
            if nome.endswith('.py'):
                yield os.path.relpath(os.path.join(radice, nome), SRC_PGE)


def test_la_lista_degli_emettitori_e_completa():
    """`MODULI_CON_PROTOCOLLO_CACHE` e' derivato, non solo dichiarato.

    Una lista scritta a mano copre chi c'era quando e' stata scritta. Un
    backend nuovo che dichiara lo stato della cache emette la stessa riga di
    protocollo e non entra nella lista da solo: la guardia resterebbe verde
    sopra un emettitore che nessuno sorveglia, e per csound e supercollider
    quella guardia e' gia' oggi l'unico presidio che la riga abbia. La lista
    va quindi confrontata con cio' che i sorgenti fanno davvero.

    Non e' un doppione dei due test qui sotto: quelli chiedono che i moduli
    *dichiarati* stampino ancora la riga, questo che non ci sia un modulo che
    la stampa **senza** essere dichiarato. Falliscono in direzioni opposte.
    """
    trovati = {
        rel for rel in _moduli_pge()
        if _print_di_protocollo(ast.parse(_sorgente(rel)))
    }
    dichiarati = set(MODULI_CON_PROTOCOLLO_CACHE)

    assert trovati == dichiarati, (
        "la lista degli emettitori della riga di protocollo non e' piu' "
        f"allineata ai sorgenti.\n  solo nei sorgenti: {sorted(trovati - dichiarati)}"
        f"\n  solo nella lista: {sorted(dichiarati - trovati)}\n"
        "Se hai aggiunto un renderer che dichiara lo stato della cache, "
        "aggiungilo a MODULI_CON_PROTOCOLLO_CACHE: vedi "
        "docs/how-to/add-renderer.md e docs/explanation/contratto-stdout.md."
    )


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


# =============================================================================
# 2a. LA DIAGNOSTICA NON VIVE SOLO IN `strategies/`
# =============================================================================
# Il test qui sopra e' scoped per *cartella*, e la cartella non e' il criterio:
# il criterio e' essere un punto di registrazione dinamica. I due coincidono per
# sei entry point su sette, e sul settimo il presidio mancava del tutto —
# `register_window_strategy` sta in `controllers/`, perche' li' sta il registry
# delle finestre. Misurato: rimettendo in quella funzione esattamente la
# `print()` che la #187 ha tolto dalle altre tre, la suite intera resta verde.
#
# La lista e' dichiarata *e* derivata, come quella degli emettitori: la
# dichiarazione dice cosa si sorveglia, il confronto coi sorgenti impedisce che
# un entry point nuovo — o spostato di cartella — resti fuori in silenzio.

MODULI_CON_REGISTRAZIONE_DINAMICA = [
    os.path.join('controllers', 'window_selection_strategy.py'),
    os.path.join('strategies', 'strategy_registry.py'),
    os.path.join('strategies', 'variation_registry.py'),
    os.path.join('strategies', 'voice_onset_strategy.py'),
    os.path.join('strategies', 'voice_pan_strategy.py'),
    os.path.join('strategies', 'voice_pitch_strategy.py'),
    os.path.join('strategies', 'voice_pointer_strategy.py'),
]


def _funzioni_di_registrazione(tree):
    """Le `def register_*_strategy(...)` di livello modulo."""
    return [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith('register_')
        and node.name.endswith('_strategy')
    ]


def test_la_lista_dei_punti_di_registrazione_e_completa():
    """`MODULI_CON_REGISTRAZIONE_DINAMICA` e' confrontata coi sorgenti.

    Un entry point nuovo, o spostato in un'altra cartella, non entra da solo in
    una lista scritta a mano — ed e' esattamente cosi' che
    `register_window_strategy` e' rimasto fuori dalla guardia per cartella.
    """
    trovati = {
        rel for rel in _moduli_pge()
        if _funzioni_di_registrazione(ast.parse(_sorgente(rel)))
    }
    dichiarati = set(MODULI_CON_REGISTRAZIONE_DINAMICA)

    assert trovati == dichiarati, (
        "la lista dei punti di registrazione dinamica non e' piu' allineata ai "
        f"sorgenti.\n  solo nei sorgenti: {sorted(trovati - dichiarati)}"
        f"\n  solo nella lista: {sorted(dichiarati - trovati)}\n"
        "Un `register_*_strategy` nuovo va aggiunto a "
        "MODULI_CON_REGISTRAZIONE_DINAMICA: la sua conferma e' diagnostica, e "
        "vedi docs/explanation/contratto-stdout.md."
    )


@pytest.mark.parametrize('relpath', MODULI_CON_REGISTRAZIONE_DINAMICA)
def test_la_registrazione_dinamica_non_stampa(relpath):
    """Nessun `print()` dentro un `register_*_strategy`, ovunque viva.

    La conferma di una registrazione dinamica e' diagnostica: va a
    `log_strategy_registration` (issue #187). Qui il criterio e' la funzione,
    non la cartella, cosi' che la porta non possa riaprirsi da un registry che
    sta altrove.
    """
    tree = ast.parse(_sorgente(relpath))

    for funzione in _funzioni_di_registrazione(tree):
        assert not _print_calls(funzione), (
            f"{relpath}: {funzione.name}() e' tornata a stampare. La conferma "
            "va a `log_strategy_registration` (issue #187), non su stdout."
        )


# =============================================================================
# 3. LA SECONDA RIGA DI PROTOCOLLO — il blocco riassuntivo
# =============================================================================
# Le righe che PGE-ui trasforma in eventi sono **due**, non una, e fin qui
# questo file ne sorvegliava una sola. L'altra e' il blocco riassuntivo di
# `cli.py`: `print(f"    {path}")` sotto «Generazione completata! N file
# generati:». Da li' `parse_render_line` ricava lo `stream-done` dell'ultimo
# stream DIRTY del giro — gli altri li chiude la riga `[CACHE]` successiva,
# l'ultimo non ha nessuna riga dopo di se'. Toglierle l'indentazione, o
# spezzarla su piu' righe, lascia quell'unico stem col pallino giallo dopo un
# render che ha fatto esattamente cio' che il pallino chiedeva.
#
# Misurato per sabotaggio: passando da `f"    {path}"` a `f"{path}"` la suite
# di PGE restava interamente verde prima di questo test.
#
# Qui la guardia e' **di comportamento** e non una lettura dei sorgenti: si
# fa scrivere alla CLI il suo riepilogo e si guardano i byte che finiscono su
# stdout, che sono esattamente quelli che PGE-ui legge. Un `print()` letto
# con `ast` direbbe che la riga esiste; solo l'output dice che esce indentata.

# Trascritta da `render_pipeline._RE_STEM_PATH` di PGE-ui. La trascrizione e'
# inevitabile — l'altro repo non e' importabile da qui — ed e' il motivo per
# cui il doc del contratto la nomina: se cambia di la', questa va aggiornata,
# ed e' un cambio di superficie pubblica con analisi d'impatto.
FORMA_PROTOCOLLO_PATH = re.compile(
    r"^\s+(.+__.+)\.(?:aif|aiff|wav|flac)\s*$", re.IGNORECASE)


# E questa e' `_RE_CACHE_LINE`, sempre di PGE-ui. Non e' un doppione di
# `PREFISSO_PROTOCOLLO_CACHE`: quella e' la guardia *stretta* che difende la
# riga per stream (pretende un `{}` in prima posizione), questa e' cio' che il
# parser davvero legge — un token qualunque senza spazi, letterale compreso.
# La differenza fra le due e' esattamente lo spazio in cui vivono
# `[CACHE] Manifest:` e `[CACHE] GC:`, che l'editor matcha e poi scarta col
# filtro sugli id dichiarati.
FORMA_PROTOCOLLO_CACHE = re.compile(r"^\[CACHE\]\s+(\S+):\s+(.+)$")


def _ha_forma_cache(forma):
    """La riga entrerebbe in `_RE_CACHE_LINE` di PGE-ui.

    Si misura sulla forma con le interpolazioni ridotte a un token: un id di
    stream e una parola letterale sono indistinguibili per quella regex, che
    e' il punto.
    """
    return forma is not None and bool(
        FORMA_PROTOCOLLO_CACHE.match(forma.replace('{}', 'x')))


def _ha_forma_di_path(forma):
    """La riga e' fatta di sola indentazione piu' un valore interpolato.

    E' la forma del blocco riassuntivo, l'altra meta' del protocollo. Qui la
    lettura statica arriva fino a un certo punto e conviene dirlo: se il path
    finisca o no in `.wav` lo decide il valore a runtime, non il sorgente.
    Percio' la direzione "questa riga e' protocollo" la misura il test di
    comportamento della sezione 3; questa funzione riconosce solo la *sagoma*
    — indentazione piu' interpolazione e nient'altro — che e' cio' che rende
    una riga candidata a essere letta come path di uno stem.
    """
    return (forma is not None and forma[:1].isspace()
            and forma.replace('{}', '').strip() == '')


def _ha_forma_di_protocollo(forma):
    """La riga entrerebbe in una delle due forme che PGE-ui riconosce.

    Le forme sono due, e questa e' l'unica funzione che lo dice: chi chiede
    "questa riga finisce nel parser dell'editor" non deve ricordarsi di
    chiederlo due volte. Chiederlo per la sola `[CACHE]` e' il modo in cui la
    meta' del blocco riassuntivo e' rimasta scoperta la prima volta.
    """
    return _ha_forma_cache(forma) or _ha_forma_di_path(forma)


def _stem_paths_su_stdout(testo):
    """Le righe di `testo` che PGE-ui leggerebbe come path di uno stem."""
    return [FORMA_PROTOCOLLO_PATH.match(r).group(1)
            for r in testo.splitlines()
            if FORMA_PROTOCOLLO_PATH.match(r)]


def test_il_blocco_riassuntivo_resta_protocollo(mocks, capsys):
    """I path degli stem escono nella forma da cui PGE-ui ricava stream-done.

    E' la seconda meta' del protocollo, e l'unica che chiude l'ultimo stream
    DIRTY del giro.
    """
    api_mod = mocks['main'].api
    result = api_mod.RenderResult(
        audio_paths=['/out/PGE_test__streamA.wav',
                     '/out/PGE_test__stream-B.2.wav'],
        elapsed_seconds=0.0, renderer_type='numpy', per_stream=True)
    argv = ['main.py', 'test.yml', 'out.wav', '--per-stream',
            '--renderer', 'numpy', '--format', 'wav']
    with patch.object(api_mod, 'render', return_value=result):
        with patch.object(sys, 'argv', argv):
            mocks['main'].main()

    trovati = _stem_paths_su_stdout(capsys.readouterr().out)

    assert trovati == ['/out/PGE_test__streamA', '/out/PGE_test__stream-B.2'], (
        "il blocco riassuntivo non esce piu' nella forma che PGE-ui parsa "
        "(`    <path>__<id>.<ext>`). E' da li' che l'editor ricava lo "
        "stream-done dell'ultimo stream DIRTY: vedi issue #178 e "
        "docs/explanation/contratto-stdout.md."
    )


def test_lo_stream_done_si_aggancia_al_suffisso_dell_id(mocks, capsys):
    """Il path deve finire per `__<id>`, che e' cio' che PGE-ui confronta.

    `parse_render_line` non cattura l'id: chiede che il path finisca per
    `"__" + <lo stream in corso>`. Un id troncato o normalizzato nel path — un
    `.`/`-` sostituito, il basename accorciato — lascia il confronto senza
    aggancio, e lo stream in volo non si chiude mai. E' lo stesso difetto che
    la `\\w` nella regex a monte aveva gia' prodotto una volta.

    Il caso e' quello che il test qui sopra non copre, ed e' anche l'unico su
    cui il confronto per suffisso si distingue da uno per gruppo catturato:
    un **basename che contiene gia' `__`**. Li' non c'e' una posizione del
    separatore da indovinare — `_RE_STEM_PATH` cattura tutto fino
    all'estensione e chi legge confronta la coda — e una `print()` che
    provasse a "ripulire" il path lo romperebbe senza che nient'altro se ne
    accorga. Senza questo caso l'asserzione era piu' debole di quella del test
    precedente sugli stessi byte: non poteva fallire da sola.
    """
    api_mod = mocks['main'].api
    result = api_mod.RenderResult(
        audio_paths=['/out/PGE__test__stream-B.2.wav'],
        elapsed_seconds=0.0, renderer_type='numpy', per_stream=True)
    argv = ['main.py', 'test.yml', 'out.wav', '--per-stream',
            '--renderer', 'numpy', '--format', 'wav']
    with patch.object(api_mod, 'render', return_value=result):
        with patch.object(sys, 'argv', argv):
            mocks['main'].main()

    trovati = _stem_paths_su_stdout(capsys.readouterr().out)

    assert trovati == ['/out/PGE__test__stream-B.2'], (
        "il path dello stem non esce piu' intero: PGE-ui confronta la coda "
        "`__<id>` su quel che la regex cattura, e un basename che contiene "
        "gia' `__` non gli da' nessun separatore da indovinare."
    )
    assert trovati[0].endswith('__stream-B.2'), (
        "il path dello stem non finisce piu' per `__<id>`: PGE-ui confronta "
        "proprio quel suffisso per chiudere lo stream in corso."
    )


# =============================================================================
# 4. LA CLASSIFICAZIONE COMPLETA — ogni print() di src/pge/ ha una categoria
# =============================================================================
# L'esito della #178 e' che *ogni* riga sappia in quale delle tre categorie
# sta. Fin qui il repo ne classificava due gruppi — la riga `[CACHE]` per
# stream (protocollo) e le registrazioni di strategy (diagnostica, #187) — e
# per tutto il resto `api.py` diceva «nessuno le parsa, per quanto se ne sa»,
# che e' la frase che questa issue doveva chiudere.
#
# La tabella e' la classificazione, in forma eseguibile. La chiave e'
# **(modulo, forma della riga)**: il numero di riga si sposta a ogni modifica
# del file, la forma no — e la forma e' anche cio' su cui il parser a valle
# decide. Due `print()` con la stessa forma nello stesso modulo sono la stessa
# riga, e condividono la categoria per costruzione.
#
# Le tre categorie sono per **destinatario**, non per contenuto:
#
#   PROTOCOLLO   il parser di PGE-ui la legge. Resta su stdout, con quella
#                forma esatta. Cambiarla e' superficie pubblica.
#   DIAGNOSTICA  la legge chi sta estendendo il motore. Puo' andare al logger.
#   INTERFACCIA  la legge a schermo chi ha lanciato il render. Resta su
#                stdout, ma non e' protocollo: nessuno la parsa.
#
# Il criterio fra le ultime due, che e' l'unico che richiede un giudizio:
# **di chi parla la riga.** Del render di chi ha lanciato il comando — cosa
# sta producendo, quanto ci ha messo, dove sono i file, cosa non andava nel
# suo YAML — o della contabilita' interna del motore. `⚡ SOLO MODE` e
# `🔇 N stream muted` sono interfaccia benche' somiglino a debug: dicono al
# compositore che il suo flag ha cambiato l'audio che sta per ascoltare.
#
# **Cosa la tabella non decide.** Dice dove una riga *sta*, non dove dovrebbe
# andare: spostare una INTERFACCIA al logger resta una scelta di prodotto —
# cambia cio' che l'utente vede — e le issue di esecuzione la prendono una
# riga alla volta. Quel che la tabella impedisce e' di spostarne una senza
# accorgersi che era protocollo.
PROTOCOLLO = 'protocollo'
DIAGNOSTICA = 'diagnostica'
INTERFACCIA = 'interfaccia'

CLASSIFICAZIONE = {
    # --- cli.py ---
    ('cli.py', '\n Generazione completata! {} file generati:'):
        INTERFACCIA,
    ('cli.py', '\n Rendering completato in {}s{}'):
        INTERFACCIA,
    ('cli.py', '\nGenerazione partitura grafica...'):
        INTERFACCIA,
    ('cli.py', '    {}'):
        PROTOCOLLO,
    ('cli.py', '  Dettagli:     {}'):
        INTERFACCIA,
    ('cli.py', '  → {}: grani non generati (cache)'):
        INTERFACCIA,
    ('cli.py', '  → {}: {} {} ({} {})'):
        INTERFACCIA,
    ('cli.py', ' Errore: {}'):
        INTERFACCIA,
    ('cli.py', "--grain-height non valido: '{}'. Valori: {}"):
        INTERFACCIA,
    ('cli.py', '--jobs deve essere >= 1, ricevuto: {}. Usa 1 per il rendering sequenziale.'):
        INTERFACCIA,
    ('cli.py', "--jobs non valido: '{}'. Usa un intero >= 1 oppure 'auto'."):
        INTERFACCIA,
    ('cli.py', '--log-dir richiede una directory. Esempio: --log-dir /percorso/ai/log'):
        INTERFACCIA,
    ('cli.py', "--magnify-at: chiave ignota '{}'. Valide: {}."):
        INTERFACCIA,
    ('cli.py', '--magnify-at: nessun target valido nello SPEC.'):
        INTERFACCIA,
    ('cli.py', "--magnify-at: ogni target richiede la chiave 't' (tempo in secondi)."):
        INTERFACCIA,
    ('cli.py', "--magnify-at: token non valido '{}'. Usa chiave=valore (es. t=14,zoom=10)."):
        INTERFACCIA,
    ('cli.py', "--magnify-at: valore non numerico per '{}': '{}'."):
        INTERFACCIA,
    ('cli.py', '--page-duration deve essere positivo, ricevuto: {}'):
        INTERFACCIA,
    ('cli.py', "--page-duration non valido: '{}'. Deve essere un numero."):
        INTERFACCIA,
    ('cli.py', '--samples-dir richiede una directory. Esempio: --samples-dir /percorso/ai/sample'):
        INTERFACCIA,
    ('cli.py', '--sc-block-size deve essere >= 1, ricevuto: {}'):
        INTERFACCIA,
    ('cli.py', "--sc-block-size non valido: '{}'. Deve essere un intero >= 1."):
        INTERFACCIA,
    ('cli.py', '--sc-max-nodes deve essere >= 1, ricevuto: {}'):
        INTERFACCIA,
    ('cli.py', "--sc-max-nodes non valido: '{}'. Deve essere un intero >= 1."):
        INTERFACCIA,
    ('cli.py', "--sv-layout non valido: '{}'. Valori: multi, single"):
        INTERFACCIA,
    ('cli.py', 'Caricamento {}...'):
        INTERFACCIA,
    ('cli.py', 'Envelope non validi: {}. Validi: {}'):
        INTERFACCIA,
    ('cli.py', "Formato non supportato: '{}'. Usa: aiff, wav, flac"):
        INTERFACCIA,
    ('cli.py', 'Generazione streams...'):
        INTERFACCIA,
    ('cli.py', 'Grain JSON: {}'):
        INTERFACCIA,
    ('cli.py', 'Log: {}'):
        INTERFACCIA,
    ('cli.py', 'Reaper project: {}'):
        INTERFACCIA,
    ('cli.py', 'Sonic Visualiser session: {}'):
        INTERFACCIA,
    ('cli.py', 'Uso: python main.py <file.yml> [output.aif] [--visualize] [--show-static] [--show-voice-offsets] [--plot-envelopes nomi,csv] [--magnify] [--magnify-at SPEC] [--page-duration SECONDI] [--grain-height duration|read-span] [--bw] [--per-stream] [--renderer csound|numpy|supercollider] [--jobs N|auto] [--format aiff|wav|flac] [--samples-dir DIR] [--log-dir DIR] [--orc-path PATH] [--incdir DIR] [--ssdir DIR] [--sfdir DIR] [--message-level N] [--keep-sco] [--sco-dir DIR] [--sc-synthdef-source PATH] [--sc-synthdef-dir DIR] [--sc-block-size N] [--sc-max-nodes N] [--keep-osc] [--osc-dir DIR] [--cache] [--cache-dir DIR] [--reaper] [--reaper-path FILE] [--grain-json] [--export-sv] [--sv-path FILE] [--sv-layout multi|single]'):
        INTERFACCIA,
    ('cli.py', '[CACHE] GC: rimossi {} stream orfani: {}'):
        PROTOCOLLO,
    ('cli.py', '[CACHE] Manifest: {}'):
        PROTOCOLLO,
    ('cli.py', '[export-sv] ignorato in modalità --per-stream (STEMS): v1 supporta solo MIX'):
        INTERFACCIA,
    ('cli.py', '[grain-json] ignorato: richiede --per-stream'):
        INTERFACCIA,
    ('cli.py', None):
        INTERFACCIA,
    # --- engine/generator.py ---
    ('engine/generator.py', "  → Stream '{}': {}"):
        DIAGNOSTICA,
    ('engine/generator.py', 'Creazione di {} stream...'):
        INTERFACCIA,
    ('engine/generator.py', '[CACHE] Stream da scrivere: {}'):
        DIAGNOSTICA,
    ('engine/generator.py', "[SEED] Nessun seed nello YAML: seed di sessione {}. Per riprodurre questo run aggiungi 'seed: {}' allo YAML."):
        INTERFACCIA,
    ('engine/generator.py', "⚠️  Warning: impossibile valutare '{}': {}"):
        INTERFACCIA,
    ('engine/generator.py', '⚡ SOLO MODE: creazione di {} stream (su {} totali)'):
        INTERFACCIA,
    ('engine/generator.py', '🔇 {} stream muted'):
        INTERFACCIA,
    # --- rendering/csound_renderer.py ---
    ('rendering/csound_renderer.py', '[CACHE] {}: {}'):
        PROTOCOLLO,
    # --- rendering/numpy_audio_renderer.py ---
    ('rendering/numpy_audio_renderer.py', '[CACHE] {}: {}'):
        PROTOCOLLO,
    # --- rendering/score_visualizer.py ---
    ('rendering/score_visualizer.py', '  Rendering pagina {}/{}...'):
        INTERFACCIA,
    ('rendering/score_visualizer.py', '  ✓ {}'):
        INTERFACCIA,
    ('rendering/score_visualizer.py', 'Analisi completata: {} pagine, durata totale {}s'):
        INTERFACCIA,
    ('rendering/score_visualizer.py', 'Esportazione PDF: {}'):
        INTERFACCIA,
    ('rendering/score_visualizer.py', 'Esportazione PNG in: {}'):
        INTERFACCIA,
    ('rendering/score_visualizer.py', '⚠️  Impossibile caricare waveform {}: {}'):
        INTERFACCIA,
    ('rendering/score_visualizer.py', '✓ PDF esportato: {}'):
        INTERFACCIA,
    # --- rendering/score_writer.py ---
    ('rendering/score_writer.py', '  - {} function tables'):
        INTERFACCIA,
    ('rendering/score_writer.py', '  - {} grani totali'):
        INTERFACCIA,
    ('rendering/score_writer.py', '  - {} streams granulari'):
        INTERFACCIA,
    ('rendering/score_writer.py', '✓ Score generato: {}'):
        INTERFACCIA,
    # --- rendering/stream_cache_manager.py ---
    ('rendering/stream_cache_manager.py', '[CACHE] {}/{} stream da ricompilare'):
        INTERFACCIA,
    ('rendering/stream_cache_manager.py', '[CACHE] {}: {}'):
        PROTOCOLLO,
    # --- rendering/supercollider_renderer.py ---
    ('rendering/supercollider_renderer.py', '[CACHE] {}: {}'):
        PROTOCOLLO,
    # --- shared/logger.py ---
    ('shared/logger.py', 'CLIP: {}'):
        INTERFACCIA,
    ('shared/logger.py', '📝 Clip log file: {}'):
        INTERFACCIA,
}


def _print_censiti():
    """Le `print()` di `src/pge/`, come (modulo, forma del primo argomento).

    `None` come forma e' un primo argomento che non e' una stringa letterale
    — `print(err.user_message())` — dove non c'e' nessun testo da leggere
    staticamente: entra comunque nel censimento, perche' la domanda della
    #178 e' «questa riga chi la legge», non «che forma ha».
    """
    censiti = set()
    for rel in _moduli_pge():
        for chiamata in _print_calls(ast.parse(_sorgente(rel))):
            forma = _template(chiamata.args[0]) if chiamata.args else None
            if chiamata.args and not isinstance(
                    chiamata.args[0], (ast.Constant, ast.JoinedStr)):
                forma = None
            censiti.add((rel, forma))
    return censiti


def test_ogni_print_di_src_pge_e_classificato():
    """Nessuna `print()` senza categoria, nessuna categoria senza `print()`.

    Le due direzioni servono entrambe, come per le liste della #187. Una
    `print()` nuova che nessuno classifica e' il modo in cui il canale e'
    tornato ambiguo la prima volta: chi la scrive non sa che sta scrivendo
    dentro l'interfaccia di un altro repository, e niente glielo dice. Una
    voce che resta in tabella dopo che la riga se n'e' andata al logger
    trasforma la classificazione in un ricordo — ed e' esattamente cio' che
    succedera' quando le issue di esecuzione cominceranno a spostarle.
    """
    trovati = _print_censiti()
    dichiarati = set(CLASSIFICAZIONE)

    assert trovati == dichiarati, (
        "la classificazione di stdout non e' piu' allineata ai sorgenti.\n"
        f"  da classificare: {sorted(trovati - dichiarati)}\n"
        f"  non piu' emesse: {sorted(dichiarati - trovati)}\n"
        "Ogni print() di src/pge/ va in CLASSIFICAZIONE come protocollo, "
        "diagnostica o interfaccia: vedi issue #178 e "
        "docs/explanation/contratto-stdout.md."
    )


def _classificazione_ordinata():
    """Le voci in ordine stabile. La chiave regge la forma `None`, che
    `sorted` da sola non sa confrontare con una stringa."""
    return sorted(CLASSIFICAZIONE.items(),
                  key=lambda voce: (voce[0][0], voce[0][1] is None, voce[0][1] or ''))


def test_solo_le_righe_di_protocollo_hanno_forma_di_protocollo():
    """Nessuna riga classificata altrimenti entra nel parser di PGE-ui.

    E' la meta' che rende la tabella qualcosa di piu' di un elenco. Le due
    forme che `render_pipeline.py` riconosce sono uno spazio di nomi
    condiviso: chiunque scriva `[CACHE] <token>: ...` ci finisce dentro,
    qualunque cosa intendesse dire — e lo stesso vale per una riga fatta di
    sola indentazione piu' un path. Classificare una riga come interfaccia
    non la tiene fuori dal parser — solo la sua forma lo fa.

    Le forme da controllare sono percio' **due**, quante ne legge il parser.
    Questo test ne guardava una: una `print(f"    {qualcosa}")` nuova, marcata
    interfaccia, sarebbe passata — ed e' esattamente la riga del blocco
    riassuntivo, cioe' l'altra meta' del protocollo.
    """
    for (modulo, forma), categoria in _classificazione_ordinata():
        if categoria == PROTOCOLLO or forma is None:
            continue
        assert not _ha_forma_di_protocollo(forma), (
            f"{modulo}: `{forma}` e' classificata {categoria} ma ha la forma "
            "che PGE-ui parsa. O e' protocollo, o va riscritta.\n"
            "Le due forme — `[CACHE] <token>: ...` e una riga di sola "
            "indentazione piu' un path — finiscono nel parser dell'editor "
            "qualunque cosa la riga intenda dire: vedi issue #178."
        )


def test_le_righe_di_protocollo_sono_quelle_che_il_parser_legge():
    """La categoria PROTOCOLLO non e' piu' larga di cio' che il parser vede.

    L'inclusione va tenuta nelle due direzioni, e questa e' quella che si
    perde: marcare protocollo una riga che nessuno parsa la congela senza
    motivo — e chi legge la tabella per sapere cosa non puo' toccare si
    ritrova a difendere prosa. Le forme ammesse sono due, e sono le due che
    `render_pipeline.py` riconosce.
    """
    for (modulo, forma), categoria in _classificazione_ordinata():
        if categoria != PROTOCOLLO:
            continue
        assert forma is not None, f"{modulo}: protocollo senza forma leggibile"
        assert _ha_forma_di_protocollo(forma), (
            f"{modulo}: `{forma}` e' marcata protocollo ma non ha nessuna "
            "delle due forme che PGE-ui parsa. Se non la legge nessuno, e' "
            "interfaccia o diagnostica."
        )


# =============================================================================
# 5. NEMMENO IL LOGGER PUO' PARLARE COME IL PROTOCOLLO
# =============================================================================
# `logger.py` e questo file hanno scritto a lungo che la diagnostica e' al
# sicuro perche' `logging` scrive su **stderr** e il protocollo vive su
# stdout. Il file descriptor pero' non e' un confine: il bridge di PGE-ui
# lancia il motore con `stderr=subprocess.STDOUT` (`RenderState.start`), quindi
# stderr e stdout arrivano allo stesso `readline`, e ogni riga passa per
# `parse_render_line`.
#
# Misurato, non dedotto. Con l'host che accende la diagnostica come chiunque
# la accenderebbe:
#
#     logging.basicConfig(level=logging.DEBUG, format="%(message)s")
#     logging.getLogger('pge.diagnostics').debug("[CACHE] %s: registrata", nome)
#
# la riga e' arrivata al parser tale e quale e ha prodotto `stream-start` +
# `stream-done` per uno stream di nome `gaussian`, che non esiste. A salvarla
# nel formato di default e' solo il prefisso `DEBUG:pge.diagnostics:` che il
# formatter antepone — cioe' una scelta dell'host, non una garanzia del
# motore: `format="%(message)s"` la toglie.
#
# Quindi la regola vera non e' «il logger e' un altro canale». E':
# **nessuno, su nessun canale, scrive righe che hanno la forma del
# protocollo.** Il censimento delle `print()` non basta a tenerla, perche' una
# riga che nasce gia' sul logger non e' una `print()`.

METODI_LOG = {'debug', 'info', 'warning', 'warn', 'error',
              'exception', 'critical', 'log'}


def _messaggi_di_log(tree):
    """I messaggi letterali passati a una chiamata di logging.

    Riconosce la forma `<qualcosa>.debug("...")` per attributo, senza
    risolvere chi sia l'oggetto: un logger vero, `self.logger`, il risultato
    di `get_diagnostic_logger()` sono tutti la stessa domanda. `.log(livello,
    msg)` porta il messaggio in seconda posizione.
    """
    messaggi = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in METODI_LOG):
            continue
        args = node.args[1:] if node.func.attr == 'log' else node.args
        if not args:
            continue
        forma = _template(args[0])
        if forma:
            # I segnaposto di `logging` sono `%s`/`%d`, non `{}`: qui contano
            # come interpolazioni esattamente come quelli di una f-string.
            messaggi.append((forma, re.sub(r'%[sdrfgi]', '{}', forma)))
    return messaggi


def test_nessun_messaggio_di_log_ha_la_forma_del_protocollo():
    """Nessuna riga di logging entrerebbe nel parser di PGE-ui.

    Il canale non protegge: il bridge unisce stderr a stdout. A separare la
    diagnostica dal protocollo resta solo la forma della riga, e questa e' la
    guardia che la tiene separata.

    Le forme sono **due**, come per le `print()`. Guardare la sola `[CACHE]`
    lasciava scoperta proprio quella che il logger scrive con piu' naturalezza:
    `log.debug("    %s", path)` — sola indentazione piu' un path — chiude
    nell'editor lo stream in volo, e lo chiude *prima* che sia finito.
    """
    colpevoli = []
    for rel in _moduli_pge():
        for originale, normalizzato in _messaggi_di_log(
                ast.parse(_sorgente(rel))):
            if _ha_forma_di_protocollo(normalizzato):
                colpevoli.append(f"{rel}: {originale!r}")

    assert not colpevoli, (
        "questi messaggi di log hanno una delle due forme che PGE-ui parsa, "
        "e stderr NON e' un riparo (il bridge lo unisce a stdout):\n  "
        + "\n  ".join(colpevoli)
        + "\nVedi docs/explanation/contratto-stdout.md, issue #178."
    )


def test_la_guardia_sui_messaggi_di_log_riconosce_i_segnaposto_di_logging():
    """`%s` conta come interpolazione, o la guardia e' cieca sul caso vero.

    Le righe di `logging` si scrivono con lo stile pigro (`"...%s..."`,
    argomenti a parte), non con una f-string, e `_messaggi_di_log` le riduce
    percio' alla stessa forma `{}` delle `print()`.

    Il caso che *misura* quella riduzione e' il blocco riassuntivo, non la
    `[CACHE]`, e conviene dire perche': per `_RE_CACHE_LINE` il token e' `\\S+`,
    e un `%s` lo soddisfa gia' cosi' com'e' — su quel ramo la normalizzazione
    non cambia verdetto, e un test scritto solo su di esso resta verde anche
    dopo averla tolta (misurato). La sagoma del path invece pretende che *tutto*
    quel che non e' indentazione sia interpolazione: li' `    %s` senza
    riduzione e' testo, e la guardia diventa cieca.
    """
    sorgente = (
        'log = get_diagnostic_logger()\n'
        'log.debug("[CACHE] %s: registrata", nome)\n'
        'log.debug("    %s", path)\n'
    )

    messaggi = _messaggi_di_log(ast.parse(sorgente))

    # Sui grezzi la seconda riga non e' riconoscibile: e' la riduzione a
    # renderla tale, ed e' questa la differenza che il test misura.
    assert [_ha_forma_di_protocollo(o) for o, _ in messaggi] == [True, False]
    assert [_ha_forma_di_protocollo(n) for _, n in messaggi] == [True, True]
