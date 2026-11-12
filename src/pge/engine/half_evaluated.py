"""
half_evaluated.py

Trova le espressioni scritte per meta' fuori dalle parentesi (issue #309).

La valutazione al caricamento (`Generator._eval_math_expressions`) sostituisce
cio' che sta fra parentesi e lascia il resto com'e': di `(10/2)/10` faceva la
stringa `5.0/10`. La regola e' che un'espressione sta tutta dentro le
parentesi esterne — la stessa delle espressioni per grano (#308) — e qui si
cerca la prima stringa del documento che la viola.

Il criterio e' l'esito, non la forma: una stringa con delle parentesi dentro,
non tutta fra parentesi, che messa INTERA fra parentesi la valutazione
trasforma in un numero. `voce (1).wav` e' fatta degli stessi caratteri di
`(10/2)/10`, ma fra parentesi non e' un numero, e resta trattata come prima.
La prova la fa chi chiama (`probe`), col metodo vero: questo modulo non
conosce ne' il regex ne' le funzioni ammesse, e non ne tiene una copia.

Le espressioni che leggono una mappa non passano di qui: attraversano il
caricamento al riparo (`expression_shelter`), dove non sono stringhe.

Si guarda dove il motore legge un numero. Un testo non e' un'espressione a
meta', nemmeno se ha la stessa forma: `title: 11 - (2026)` si caricava, e
l'errore gli proponeva di diventare il numero -2015. Fuori dagli stream il
motore legge solo le chiavi di `ENGINE_TOP_LEVEL_KEYS`; dentro uno stream
sono testo per definizione quelle di `STREAM_TEXT_KEYS`.
"""
from __future__ import annotations

from typing import Callable, NamedTuple, Optional

from pge.expressions.expression import outer_parenthesized


#: Le chiavi in testa al documento che il motore legge, oltre a `streams`.
#: Tutto il resto (`composition`, `title`, appunti) e' di chi scrive lo YAML.
ENGINE_TOP_LEVEL_KEYS = ('seed',)

#: Le chiavi di uno stream che sono testo: un'identita' e il nome di un file.
STREAM_TEXT_KEYS = ('stream_id', 'sample')


class HalfEvaluated(NamedTuple):
    """Una stringa che il caricamento valuterebbe a meta'."""
    #: il testo com'e' scritto nello YAML
    text: str
    #: il path YAML: dentro lo stream (`grain.duration`, `volume[1][0]`) se
    #: la stringa sta in uno stream, dalla testa del documento altrimenti
    field: str
    #: la posizione dello stream in `streams:`, o None
    stream_index: Optional[int]
    #: lo `stream_id` com'e' scritto, o None
    stream_id: Optional[str]


def _sospetta(testo: str) -> bool:
    """Ha delle parentesi, e non sta tutta dentro una coppia esterna."""
    return ('(' in testo and ')' in testo
            and not outer_parenthesized(testo))


def _cerca(obj, percorso: str, probe) -> Optional[tuple]:
    """La prima stringa valutata a meta' sotto `obj`: `(testo, path)`."""
    if isinstance(obj, dict):
        for chiave, valore in obj.items():
            sotto = f"{percorso}.{chiave}" if percorso else str(chiave)
            trovata = _cerca(valore, sotto, probe)
            if trovata is not None:
                return trovata
        return None
    if isinstance(obj, list):
        for indice, valore in enumerate(obj):
            trovata = _cerca(valore, f"{percorso}[{indice}]", probe)
            if trovata is not None:
                return trovata
        return None
    if isinstance(obj, str) and _sospetta(obj) and probe(obj) is not None:
        return obj, percorso
    return None


def _senza_testo(stream):
    """Lo stream senza le chiavi che sono testo (`STREAM_TEXT_KEYS`)."""
    if not isinstance(stream, dict):
        return stream
    return {chiave: valore for chiave, valore in stream.items()
            if chiave not in STREAM_TEXT_KEYS}


def find_half_evaluated(
    document, probe: Callable[[str], Optional[float]],
) -> Optional[HalfEvaluated]:
    """La prima espressione valutata a meta' del documento, o None.

    Args:
        document: il documento YAML, con le espressioni per grano gia' al
            riparo.
        probe: `testo -> numero | None`: il testo messo intero fra parentesi
            e valutato come lo valuta il caricamento.
    """
    if not isinstance(document, dict):
        return None
    for chiave, valore in document.items():
        if chiave == 'streams' and isinstance(valore, list):
            for indice, stream in enumerate(valore):
                trovata = _cerca(_senza_testo(stream), '', probe)
                if trovata is not None:
                    stream_id = (stream.get('stream_id')
                                 if isinstance(stream, dict) else None)
                    return HalfEvaluated(
                        trovata[0], trovata[1], indice,
                        None if stream_id is None else str(stream_id))
            continue
        if chiave not in ENGINE_TOP_LEVEL_KEYS:
            continue
        trovata = _cerca(valore, str(chiave), probe)
        if trovata is not None:
            return HalfEvaluated(trovata[0], trovata[1], None, None)
    return None
