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

A queste si aggiungono alcuni **guard di arita'** sulle macro-forme (quanti
punti ha un gruppo, quanti cicli un formato compatto) e la costruzione anticipata
della distribuzione temporale. Non sono una seconda validazione del builder:
sono li' perche' quelle stesse condizioni, lasciate al builder, risalgono come
`ValueError` nudi — fuori dalla gerarchia `EngineError`, senza campo e senza
stream_id.

La copertura non e' totale e non va dichiarata tale: restano al builder le
condizioni che dipendono da quanto ha gia' percorso (`end_time` contro l'offset
accumulato dagli elementi precedenti) e le distribuzioni che validano i propri
parametri solo all'uso.

La normalizzazione avvolge il valore in `{'type': 'step', 'points': <raw>}`.
Il wrapping preserva la semantica temporale: `create_scaled_envelope` sul dict
legge `time_unit` con fallback su `time_mode`, cioe' esattamente cio' che fa
sulla lista nuda.
"""
from __future__ import annotations

from typing import Any, Union

from pge.envelopes.envelope_builder import EnvelopeBuilder
from pge.envelopes.time_distribution import TimeDistributionFactory
from pge.shared.exceptions import EngineError, InvalidFieldValueError

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

# Guard di arita'. Sollevati qui e non lasciati al builder perche' di la'
# risalgono come ValueError nudi, fuori dalla gerarchia EngineError: senza
# campo, senza stream_id, e con un messaggio che PGE-ls non puo' attribuire.

_GROUP_ARITY_HINT = (
    "un BP group di grain.read_direction richiede almeno 2 punti: con meno "
    "non ha segmenti interni, quindi non c'e' nessuna zona a cui applicare "
    "l'interpolazione. Per un verso costante basta lo scalare (-1 o +1)."
)

_REPS_ARITY_HINT = (
    "il numero di ripetizioni del formato compatto e' un intero >= 1: con "
    "zero o meno cicli non c'e' nessun breakpoint da generare. Il resto della "
    "coerenza temporale del ciclo (end_time contro l'istante da cui parte) "
    "resta al builder, che e' l'unico a conoscere l'offset accumulato dagli "
    "elementi precedenti."
)

_DIST_HINT = (
    "la distribuzione temporale del formato compatto non e' costruibile: {err}. "
    "Il verso di lettura non ha una distribuzione propria — e' quella "
    "dell'envelope, e le forme valide sono quelle di sempre."
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
    """Un valore dichiarato — scalare o Y di un breakpoint — vale -1 o +1."""
    if not _is_number(value) or float(value) not in READ_DIRECTION_VALUES:
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

    - dentro un BP group basta il riconoscimento della forma: `_is_bp_group`
      pretende che ogni punto sia `[num, num]` o `[num, num, str]`, quindi un
      annidamento fa fallire il riconoscimento e il valore non arriva mai a
      chiamarsi gruppo;
    - dentro il pattern di un ciclo no: `_is_compact_format` filtra i punti
      sulla sola lunghezza (2 o 3), e un BP group e' lungo 2. Li' il rifiuto lo
      fa `_check_pattern_point`, altrimenti il valore passa di qui e muore nel
      builder con un TypeError nudo.
    """
    if EnvelopeBuilder._is_compact_format(body):
        _check_compact(body)
        return

    if EnvelopeBuilder._is_bp_group(body):
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
    if EnvelopeBuilder._is_compact_format(item):
        _check_compact(item)
        return

    if EnvelopeBuilder._is_bp_group(item):
        _check_bp_group(item)
        return

    if EnvelopeBuilder._is_3tuple_breakpoint(item):
        # Tag per-punto (issue #54): il type governa il segmento uscente.
        _check_interp(item[2])
        _check_direction_value(item[1])
        return

    if isinstance(item, dict) and 't' in item and 'v' in item:
        _check_interp(item.get('type'))
        _check_direction_value(item['v'])
        return

    if isinstance(item, list) and len(item) == 2 and _is_number(item[0]):
        _check_direction_value(item[1])
        return

    _reject(item, _FORM_HINT)


def _check_bp_group(group: list) -> None:
    """BP group (issue #64): `[points, interp]`, interp della macrozona."""
    points, interp = group
    _check_interp(interp)
    # Solo l'arita': che `points` sia una lista di breakpoint piatti lo
    # garantisce gia' `_is_bp_group`, che qui e' sempre passato.
    if len(points) < 2:
        _reject(points, _GROUP_ARITY_HINT)
    _check_points(points)


def _check_compact(compact: list) -> None:
    """Formato compatto: l'interp e' il quarto elemento, i valori stanno nel
    pattern. `end_time` non e' un verso e non si valida qui (vedi
    `_REPS_ARITY_HINT`)."""
    pattern = compact[0]
    n_reps = compact[2]
    interp = compact[3] if len(compact) >= 4 else None
    time_dist = compact[4] if len(compact) >= 5 else None
    _check_interp(interp)
    if n_reps < 1:
        _reject(n_reps, _REPS_ARITY_HINT)
    if not pattern:
        _reject(pattern, _FORM_HINT)
    for point in pattern:
        _check_pattern_point(point)
    _check_time_dist(time_dist)


def _check_time_dist(spec: Any) -> None:
    """La distribuzione temporale del ciclo: la valida il factory, costruendola.

    Qui non c'e' niente da decidere — il verso di lettura non ha una
    distribuzione propria, e' quella dell'envelope. Ma `_is_compact_format`
    accetta in quella posizione qualunque `str` o `dict`, e cio' che ne esce
    fallisce dentro `TimeDistributionFactory` con errori fuori dalla gerarchia
    `EngineError`. Costruirla adesso li fa risalire dove hanno un campo.

    E' delega, non duplicazione: il registro delle distribuzioni e i vincoli
    sui loro parametri restano uno solo, e questo guard resta allineato da se'
    se cambiano. I costruttori sono puri (validano e assegnano), quindi il
    costo e' un oggetto buttato via.

    Resta scoperta una distribuzione che accetti tutto nel costruttore e
    fallisca all'uso: oggi `power`, che non valida `exponent` e sbaglia dentro
    `calculate_distribution`, con un `total_time` che dipende dall'offset
    accumulato e che di qui non si conosce. E' lo stesso confine di `end_time`.
    """
    try:
        TimeDistributionFactory.create(spec)
    except EngineError:
        # Gia' dentro la gerarchia: ha campo, hint e prende lo stream_id.
        # Riavvolgerla perderebbe il bound che ha appena nominato.
        raise
    except Exception as err:
        # Largo di proposito: qualunque modo in cui il factory rifiuta questo
        # dato e' un rifiuto di cio' che l'utente ha scritto, non un caso da
        # enumerare a mano. Il messaggio originale finisce nell'hint.
        _reject(spec, _DIST_HINT.format(err=err))


def _check_pattern_point(point: list) -> None:
    """Un punto del pattern di un ciclo: `[x%, y]` o `[x%, y, type]`, piatto.

    Non passa da `_check_item` perche' li' le macro-forme sono ammesse, e qui
    non lo sono: `_is_compact_format` filtra i punti del pattern sulla sola
    lunghezza (2 o 3) e un BP group e' lungo 2, quindi ci si infila: il builder
    poi fa `x_pct / 100.0` sul primo elemento e solleva un TypeError nudo.
    """
    if not _is_number(point[0]):
        _reject(point, _FORM_HINT)
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
