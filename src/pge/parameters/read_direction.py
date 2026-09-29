"""
read_direction.py

Validazione e normalizzazione del valore grezzo di `grain.read_direction`
(issue #207): il verso di lettura INTERNO al grano, dichiarato come funzione
del tempo.

Unico punto del sistema che legge il valore grezzo di questa chiave, per lo
stesso motivo per cui `Stream._pre_normalize_grain_params` e' l'unico a leggere
`grain.duration_unit`: qui non si sintetizza un valore, si decide come vanno
interpretati quelli scritti.

La chiave ha due stati — `-1` lettura all'indietro, `+1` lettura in avanti — e
da questa natura discendono le due regole che il modulo fa rispettare, sempre
come errore esplicito e mai come correzione silenziosa:

1. **`step` e' l'interpolazione, non un'opzione.** E' il default implicito
   (l'envelope si scrive come una spezzata qualsiasi) ed e' l'unico interp
   ammesso: dichiarare `linear` o `cubic` — in forma dict, per-punto (issue
   #54) o BP group (issue #64) — solleva `InvalidFieldValueError`. Un valore
   intermedio fra -1 e +1 non e' un verso, quindi una rampa fra i due non ha
   niente da produrre.

2. **I valori dichiarati stanno in {-1, +1}.** Con `step` imposto l'envelope
   emette solo i valori scritti ai breakpoint: il problema non e' piu'
   l'interpolazione ma la dichiarazione. Arrotondare al segno significherebbe
   accettare una scrittura e renderizzarne un'altra; `0` poi non ha un segno e
   non ha una risposta non arbitraria.

Sono gli unici guard del modulo, perche' sono gli unici che sanno qualcosa del
verso di lettura. Quelli sulla **forma** — quanti punti ha un gruppo, quanti
cicli e fino a quando dura un formato compatto, dove cadono le percentuali del
suo pattern, se la distribuzione temporale si costruisce — vivevano qui fino a
#211, e solo qui: lo stesso corpo sotto qualunque altra chiave risaliva come
`ValueError` nudo o si rendeva in silenzio. Stanno in `EnvelopeBuilder`, che li
applica a ogni chiave e nomina il campo che gli passa l'orchestratore; per
questa chiave l'errore resta quello di prima — `InvalidFieldValueError` su
`grain.read_direction`, con lo stream — ma arriva dal builder, dopo i guard di
dominio di questo modulo.

Del corpo questo modulo percorre quanto serve a trovare gli interp e i valori:
riconosce gli elementi di una lista e rifiuta quelli che non sa leggere, ma di
un punto del pattern di un ciclo non giudica la forma (vedi
`_check_pattern_point`).

La normalizzazione avvolge il valore in `{'type': 'step', 'points': <raw>}`.
Il wrapping preserva la semantica temporale: `create_scaled_envelope` sul dict
legge `time_unit` con fallback su `time_mode`, cioe' esattamente cio' che fa
sulla lista nuda.
"""
from __future__ import annotations

from typing import Any, Union

from pge.envelopes.envelope_builder import EnvelopeBuilder
from pge.shared.exceptions import InvalidFieldValueError

# Il nome della chiave nello YAML: identita' del campo in ogni errore.
READ_DIRECTION_FIELD = 'grain.read_direction'

# I due soli valori dichiarabili.
READ_DIRECTION_VALUES = (-1.0, 1.0)

# L'unica interpolazione ammessa, e quella imposta.
REQUIRED_INTERP = 'step'

_INTERP_HINT = (
    "grain.read_direction ammette solo l'interpolazione 'step', che e' gia' "
    "implicita: il verso di lettura ha due stati, non una rampa fra i due, e "
    "un valore intermedio fra -1 e +1 non e' un verso. Togli il tipo "
    "dichiarato (l'envelope si scrive come una spezzata qualsiasi) oppure "
    "scrivi 'step', che e' ridondante ma valido."
)

_VALUE_HINT = (
    "grain.read_direction ammette solo -1 (lettura all'indietro) e +1 "
    "(lettura in avanti). Il verso non ha valori intermedi e lo 0 non ha un "
    "segno: non c'e' arrotondamento che non sia arbitrario. Per il verso che "
    "segue la testina, ometti la chiave (modalita' 'auto')."
)

_FORM_HINT = (
    "grain.read_direction accetta uno scalare (-1 o +1) oppure un envelope "
    "nelle forme note: lista di breakpoint [[t, v], ...], dict "
    "{points: [...]}, BP group o formato compatto."
)


def _is_number(value: Any) -> bool:
    """Numero vero: `bool` e' sottoclasse di `int`, ma `true` non e' `+1`."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _reject(value: Any, hint: str) -> None:
    raise InvalidFieldValueError(
        field=READ_DIRECTION_FIELD,
        value=value,
        hint=hint,
    )


def _check_direction_value(value: Any) -> None:
    """Un valore dichiarato — scalare o Y di un breakpoint — vale -1 o +1.

    Il confronto e' sull'appartenenza e non converte: `float()` su un `int`
    piu' grande di ogni double alza `OverflowError`, cioe' un errore senza
    campo sollevato proprio da chi deve produrne uno che ce l'ha. `1 == 1.0`
    in Python, quindi il confronto misto costa niente in leggibilita'.
    """
    if not _is_number(value) or value not in READ_DIRECTION_VALUES:
        _reject(value, _VALUE_HINT)


def _check_interp(interp: Any) -> None:
    """Un interp dichiarato — dovunque sia dichiarato — vale 'step'."""
    if interp is None:
        return
    if interp != REQUIRED_INTERP:
        _reject(interp, _INTERP_HINT)


def _check_envelope_body(body: Any) -> None:
    """Il corpo di un envelope: una macro-forma, oppure una lista di elementi.

    Punto unico della grammatica dei due ingressi — `{points: ...}` e lista
    nuda. Tenerne uno solo evita che divergano: `Envelope` costruisce entrambe
    le forme (un formato compatto dentro `points` e' l'esempio nel suo
    docstring), quindi un ingresso piu' stretto dell'altro rifiuterebbe uno
    YAML che il motore renderizza — e lo rifiuterebbe con un hint che elenca
    fra le forme valide proprio quella appena scartata.

    Le macro-forme sono riconosciute qui in cima e, da `_check_item`, come
    elementi di una lista mista: le stesse due posizioni in cui le riconosce
    `EnvelopeBuilder.parse`. Piu' in fondo non sono ammesse, ma per due ragioni
    diverse, che vale la pena non confondere:

    - dentro un BP group basta il riconoscimento della forma: `is_bp_group`
      pretende che ogni punto sia `[num, num]` o `[num, num, str]`, quindi un
      annidamento fa fallire il riconoscimento e il valore non arriva mai a
      chiamarsi gruppo;
    - dentro il pattern di un ciclo no: `is_compact_format` filtra i punti
      sulla sola lunghezza (2 o 3), e un BP group e' lungo 2. Li' il rifiuto e'
      del builder, che la forma del pattern la giudica per ogni chiave (issue
      #211): `_check_pattern_point` si limita a non leggere un y da un punto
      che non e' piatto.
    """
    if EnvelopeBuilder.is_compact_format(body):
        _check_compact(body)
        return

    if EnvelopeBuilder.is_bp_group(body):
        _check_bp_group(body)
        return

    _check_points(body)


def _check_points(points: Any) -> None:
    """Percorre una lista di elementi envelope, qualunque forma abbiano."""
    if not isinstance(points, list) or not points:
        _reject(points, _FORM_HINT)

    for item in points:
        _check_item(item)


def _check_item(item: Any) -> None:
    """Un elemento della lista: breakpoint, gruppo, ciclo compatto o dict."""
    if EnvelopeBuilder.is_compact_format(item):
        _check_compact(item)
        return

    if EnvelopeBuilder.is_bp_group(item):
        _check_bp_group(item)
        return

    if EnvelopeBuilder.is_3tuple_breakpoint(item):
        # Tag per-punto (issue #54): il type governa il segmento uscente.
        _check_interp(item[2])
        _check_direction_value(item[1])
        return

    if isinstance(item, dict) and 't' in item and 'v' in item:
        # Il tempo si pretende numerico come nella forma lista: e' la stessa
        # grandezza scritta in un altro modo, e un `[t, v]` con la t non
        # numerica qui sotto non verrebbe riconosciuto come breakpoint. Il
        # builder lo rifiuterebbe comunque (da #211 nominando il campo): il
        # rifiuto sta qui perche' qui si riconoscono gli elementi, per
        # leggerne il valore.
        if not _is_number(item['t']):
            _reject(item, _FORM_HINT)
        _check_interp(item.get('type'))
        _check_direction_value(item['v'])
        return

    if isinstance(item, list) and len(item) == 2 and _is_number(item[0]):
        _check_direction_value(item[1])
        return

    _reject(item, _FORM_HINT)


def _check_bp_group(group: list) -> None:
    """BP group (issue #64): `[points, interp]`, interp della macrozona.

    Che `points` sia una lista di breakpoint piatti lo garantisce gia'
    `is_bp_group`, che qui e' sempre passato; quanti debbano essere lo dice il
    builder (issue #211). Per questo i punti si percorrono uno a uno invece che
    con `_check_points`, che una lista vuota la rifiuterebbe come forma
    sconosciuta: un gruppo senza punti e' un gruppo con troppo pochi punti, e
    l'hint giusto e' quello del builder.
    """
    points, interp = group
    _check_interp(interp)
    for item in points:
        _check_item(item)


def _check_compact(compact: list) -> None:
    """Formato compatto: l'interp e' il quarto elemento, i valori stanno nel
    pattern. Il resto dello slot — `end_time`, `n_reps`, la distribuzione
    temporale, la forma del pattern — e' forma, e lo giudica il builder per
    ogni chiave (issue #211).

    Gli slot si leggono dalle costanti di `EnvelopeBuilder` (issue #213): il
    layout della tupla e' suo, e questo modulo lo percorre, non lo ridefinisce.
    Con una copia propria degli indici, un giorno che l'interp cambiasse
    posizione questa funzione avrebbe continuato a controllare lo slot vecchio
    — in silenzio, perche' li' dentro ci sarebbe stato comunque qualcosa di
    plausibile."""
    pattern = compact[EnvelopeBuilder.COMPACT_PATTERN]
    interp = (compact[EnvelopeBuilder.COMPACT_INTERP]
              if len(compact) > EnvelopeBuilder.COMPACT_INTERP else None)
    _check_interp(interp)
    for point in pattern:
        _check_pattern_point(point)


def _check_pattern_point(point: list) -> None:
    """Un punto del pattern di un ciclo: `[x%, y]` o `[x%, y, type]`.

    Non passa da `_check_item` perche' li' le macro-forme sono ammesse, e qui
    non lo sono. Ma la forma del punto non e' affare di questo modulo: la x —
    che sia un numero, in `[0, 100]`, non all'indietro — la giudica il builder
    per ogni chiave (issue #211). Qui si leggono interp e y, e solo da un punto
    la cui x e' un numero: da un BP group infilato nel pattern (`is_compact_format`
    filtra i punti sulla sola lunghezza, e un gruppo e' lungo 2) il "y" sarebbe
    la stringa del suo interp, e l'errore direbbe che `'step'` non e' un verso
    invece di dire che quello non e' un punto. Un punto cosi' non passa
    comunque: arriva al builder, che lo rifiuta nominandolo.
    """
    if not _is_number(point[0]):
        return
    if len(point) == 3:
        _check_interp(point[2])
    _check_direction_value(point[1])


def normalize_read_direction(raw: Any) -> Union[float, dict]:
    """
    Valida il valore grezzo di `grain.read_direction` e lo normalizza a `step`.

    Args:
        raw: valore letto dallo YAML — scalare o envelope in una delle forme
            note (lista di breakpoint, dict, BP group, formato compatto).

    Returns:
        float: se il valore e' scalare (-1.0 o +1.0);
        dict: `{'type': 'step', 'points': <raw>}` per ogni forma envelope, con
        le eventuali altre chiavi del dict originale (es. `time_unit`)
        preservate.

    Raises:
        InvalidFieldValueError: chiave vuota, forma non riconosciuta, interp
            diverso da `step` o valore fuori da {-1, +1}.
    """
    if raw is None:
        _reject(raw, _VALUE_HINT)

    if _is_number(raw):
        _check_direction_value(raw)
        return float(raw)

    if isinstance(raw, dict):
        if 'points' not in raw:
            _reject(raw, _FORM_HINT)
        _check_interp(raw.get('type'))
        _check_envelope_body(raw['points'])
        return {**raw, 'type': REQUIRED_INTERP}

    if isinstance(raw, list):
        _check_envelope_body(raw)
        return {'type': REQUIRED_INTERP, 'points': raw}

    _reject(raw, _FORM_HINT)
