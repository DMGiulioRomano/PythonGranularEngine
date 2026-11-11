"""
expression_shelter.py

Mette al riparo le espressioni che si valutano a ogni grano dalla valutazione
al caricamento (issue #308).

`Generator._eval_math_expressions` valuta al caricamento ogni `( ... )` di
ogni stringa in una costante: `(10/2)` diventa 5. Un'espressione che nomina
una mappa non e' una costante — `(0.02 + 0.08*m1)` vale una cosa diversa a
ogni grano — e la compila il parser dei parametri. Passata di li' resterebbe
com'e' lo stesso, ma dopo due danni:

- la riga `impossibile valutare` su stdout, per ogni espressione valida.
  Stdout e' un contratto, e PGE-ui lo legge;
- una costante dentro l'espressione valutata per conto suo:
  `(clip(m1, (1/2), 1))` uscirebbe riscritta, cioe' con un testo diverso da
  quello dello YAML negli errori e nel fingerprint.

`_eval_math_expressions` resta un metodo che sta in piedi da solo: PGE-ls ne
specchia il regex carattere per carattere e la esegue estratta dall'AST, coi
soli `math` e `re` (#269). Le espressioni si tolgono prima e si rimettono
dopo: al loro posto passa un oggetto che non e' una stringa, e che la
valutazione lascia attraversare. (La #309 ha messo la virgola nel suo regex:
da allora `(clip(m1, 0, 1))` gli somiglia per intero, e il riparo e' cio'
che la tiene fuori.)

Cosa va al riparo, dentro uno stream, fra le stringhe **tutte fra
parentesi**:

- dovunque, quelle che nominano **una mappa dichiarata in quello stream**, o
  `t` (il tempo, che e' un nome del linguaggio anche senza mappe);
- nei campi in cui un'espressione vale (`EXPRESSION_FIELDS`), anche quelle
  che nominano qualcosa che la valutazione al caricamento non conosce
  (`LOAD_TIME_NAMES`): `(0.02 + 0.08*sqrt(0.25))` e' un'espressione valida,
  ma la valutazione non sa che cosa sia `sqrt`, avvisava
  `impossibile valutare` su stdout, e poi l'interprete la compilava lo
  stesso. Un nome sbagliato (`pii`) lo dice l'interprete, coi nomi che ci
  sono, al posto dell'avviso.

Il resto — le espressioni di oggi, i nomi dei file, uno stream senza mappe
che non scrive `t` — passa dalla valutazione esattamente come prima. Anche
nei campi a espressione una costante che la valutazione sa fare (`(10/2)`,
`(0.05 * abs(-1))`) resta sua e diventa un numero: e' il numero che la
partitura disegna e che i bounds controllano al parse. Fuori da quei campi
l'avviso resta, perche' li' e' l'unica spiegazione di una stringa che non
diventa un numero.
"""
from __future__ import annotations

import re

from pge.expressions.expression import NAME_PATTERN, outer_parenthesized
from pge.expressions.fields import EXPRESSION_FIELDS

# Un nome, non un pezzo di numero: in `1e3` la `e3` non e' un nome.
_NOMI = re.compile(rf'(?<![A-Za-z_0-9.]){NAME_PATTERN}')

_TEMPO = 't'

#: I nomi che la valutazione al caricamento conosce: le chiavi del
#: `safe_dict` di `Generator._eval_math_expressions`. Una copia, perche' quel
#: metodo non importa niente del motore (PGE-ls lo esegue estratto dall'AST,
#: #269); un test la confronta col sorgente, cosi' se la valutazione cambia
#: lo si vede. La #309 non le ha toccate: ha aggiunto la virgola al regex.
LOAD_TIME_NAMES = frozenset({
    'abs', 'int', 'float', 'min', 'max', 'pow', 'pi', 'e'})

_CAMPI = frozenset(EXPRESSION_FIELDS)


class ShelteredExpression:
    """Un'espressione messa al riparo. Non e' una `str` di proposito: la
    valutazione al caricamento tocca le stringhe e lascia passare il resto."""

    __slots__ = ('text',)

    def __init__(self, text: str):
        self.text = text

    def __repr__(self) -> str:
        return f"ShelteredExpression({self.text!r})"


def _nomi_di(stream: dict) -> frozenset:
    maps = stream.get('maps')
    dichiarate = (
        {nome for nome in maps if isinstance(nome, str)}
        if isinstance(maps, dict) else set())
    return frozenset(dichiarate | {_TEMPO})


def _da_riparare(testo: str, nomi: frozenset, campo: bool) -> bool:
    """`campo`: la stringa e' il valore di uno dei campi in cui
    un'espressione vale."""
    if not outer_parenthesized(testo):
        return False
    letti = {nome.split('.')[0] for nome in _NOMI.findall(testo)}
    if letti & nomi:
        return True
    return campo and not letti <= LOAD_TIME_NAMES


def _ripara(obj, nomi: frozenset, percorso=''):
    """`percorso` e' il path YAML dentro lo stream (`grain.duration`);
    None dentro una lista, che non e' il valore di un campo ma un suo pezzo
    (un breakpoint)."""
    if isinstance(obj, dict):
        return {
            k: _ripara(v, nomi, (f"{percorso}.{k}" if percorso else k)
                       if percorso is not None and isinstance(k, str)
                       else None)
            for k, v in obj.items()}
    if isinstance(obj, list):
        return [_ripara(v, nomi, None) for v in obj]
    if isinstance(obj, str) and _da_riparare(obj, nomi, percorso in _CAMPI):
        return ShelteredExpression(obj)
    return obj


def shelter_expressions(document):
    """Il documento con le espressioni degli stream messe al riparo.

    Non muta l'originale. Un documento che non ha una lista `streams:` torna
    com'e': dira' la sua il resto del caricamento.
    """
    if not isinstance(document, dict):
        return document
    streams = document.get('streams')
    if not isinstance(streams, list):
        return document
    riparato = dict(document)
    riparato['streams'] = [
        _ripara(stream, _nomi_di(stream)) if isinstance(stream, dict)
        else stream
        for stream in streams
    ]
    return riparato


def unshelter_expressions(obj):
    """Rimette le espressioni al loro posto, come stringhe."""
    if isinstance(obj, ShelteredExpression):
        return obj.text
    if isinstance(obj, dict):
        return {k: unshelter_expressions(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [unshelter_expressions(v) for v in obj]
    return obj
