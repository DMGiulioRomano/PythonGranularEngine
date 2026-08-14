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
    """Un valore dichiarato — scalare o Y di un breakpoint — vale -1 o +1."""
    if not _is_number(value) or float(value) not in READ_DIRECTION_VALUES:
        _reject(value, _VALUE_HINT)


def _check_interp(interp: Any) -> None:
    """Un interp dichiarato — dovunque sia dichiarato — vale 'step'."""
    if interp is None:
        return
    if interp != REQUIRED_INTERP:
        _reject(interp, _INTERP_HINT)


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
    _check_points(points)


def _check_compact(compact: list) -> None:
    """Formato compatto: l'interp e' il quarto elemento, i valori stanno nel
    pattern. `end_time` e `n_reps` non sono versi e non si validano."""
    pattern = compact[0]
    interp = compact[3] if len(compact) >= 4 else None
    _check_interp(interp)
    _check_points(pattern)


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
        _check_points(raw['points'])
        return {**raw, 'type': REQUIRED_INTERP}

    if isinstance(raw, list):
        if not raw:
            _reject(raw, _FORM_HINT)
        if EnvelopeBuilder._is_compact_format(raw):
            _check_compact(raw)
        elif EnvelopeBuilder._is_bp_group(raw):
            _check_bp_group(raw)
        else:
            _check_points(raw)
        return {'type': REQUIRED_INTERP, 'points': raw}

    _reject(raw, _FORM_HINT)
