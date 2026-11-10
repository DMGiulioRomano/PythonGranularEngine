"""
map_set.py

Le mappe di uno stream (issue #307): il blocco `maps:`, lo stato, chi le
muove e chi le legge.

    maps:
      m1: {type: logistic, r: 3.5}

`MapSet` e' l'insieme delle mappe dichiarate da uno stream. Fa tre cose:

- **le costruisce** dallo YAML (`from_yaml`), rifiutando un blocco scritto
  male con un `MapConfigError` che dice dove e cosa;
- **le muove** in un punto solo (`advance`), chiamato dallo Stream in testa al
  giro di ogni voce: una mappa a `clock: grain` fa un passo per grano e per
  voce, e ha percio' **uno stato per voce**. Con piu' voci e `scatter` i
  cursori divergono e le chiamate arrivano fuori ordine: uno stato condiviso
  verrebbe iterato in ordine mescolato;
- **le fa leggere** (`value`, `environment`) senza muoverle: l'ordine in cui i
  parametri di un grano leggono la stessa mappa non conta, e due parametri
  che la leggono vedono lo stesso valore.

Lo stato iniziale e' `x0` (default del tipo) dopo un transitorio di
`transient` passi scartati (default 300, come nel banco): il primo grano e'
gia' sull'attrattore.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Tuple

from pge.expressions.expression import CONSTANTS, FUNCTIONS
from pge.maps.catalog import MAP_KINDS, MAP_TYPES, MapKind
from pge.shared.exceptions import MapConfigError
from pge.shared.logger import log_map_escape_warning

#: Le chiavi di una mappa, come letterale (vedi MAP_TYPES).
MAP_KEYS = ('type', 'r', 'clock', 'x0', 'transient')

#: `clock: grain`: un passo ogni volta che nasce un grano. E' il default.
MAP_CLOCK_GRAIN = 'grain'

#: Passi scartati prima del primo grano, quando `transient` non e' scritto.
MAP_TRANSIENT_DEFAULT = 300

#: Oltre questo modulo (o su un non-finito) la mappa e' scappata: riparte da
#: `x0`. E' la soglia del banco.
MAP_ESCAPE_LIMIT = 1e3

#: Ogni quanti secondi di tempo-stream la fuga si riscrive sul clip log.
#: Stesso valore e stesso motivo di DENSITY_NOTICE_INTERVAL: una mappa che
#: scappa lo fa a ogni manciata di grani.
MAP_ESCAPE_LOG_INTERVAL = 5.0

#: Il nome con cui un'espressione legge il tempo (secondi dall'inizio dello
#: stream).
TIME_NAME = 't'

#: Nomi che una mappa non puo' prendere: in un'espressione sono gia' una
#: funzione, una costante o il tempo, e `x`, `y`, `r` sono le variabili
#: dell'equazione di una mappa.
RESERVED_MAP_NAMES = (
    frozenset(FUNCTIONS) | frozenset(CONSTANTS)
    | frozenset({TIME_NAME, 'x', 'y', 'r'}))

_NOME = re.compile(r'[A-Za-z_][A-Za-z_0-9]*\Z')
_ASSENTE = object()


def _numero(valore) -> bool:
    return isinstance(valore, (int, float)) and not isinstance(valore, bool)


@dataclass(frozen=True)
class MapDefinition:
    """Una mappa come lo YAML la dichiara, gia' validata."""
    name: str
    kind: MapKind
    r: float
    x0: float
    transient: int


# =============================================================================
# PARSE
# =============================================================================

def _finito(valore, campo: str) -> float:
    if not _numero(valore):
        raise MapConfigError(campo, "atteso un numero", value=valore)
    if not math.isfinite(valore):
        raise MapConfigError(campo, "atteso un numero finito", value=valore)
    return float(valore)


def _definizione(nome, grezza) -> MapDefinition:
    campo = f"maps.{nome}"
    if not isinstance(nome, str) or not _NOME.match(nome):
        raise MapConfigError(
            campo, "il nome di una mappa e' fatto di lettere, cifre e `_`, "
            "e non comincia con una cifra", value=nome)
    if nome in RESERVED_MAP_NAMES:
        raise MapConfigError(
            campo, "nome riservato: in un'espressione vuol dire gia' "
            "un'altra cosa", value=nome,
            hint=f"riservati: {', '.join(sorted(RESERVED_MAP_NAMES))}")
    if not isinstance(grezza, dict):
        raise MapConfigError(
            campo, "una mappa e' un dizionario (type, r, ...)", value=grezza)

    for chiave in grezza:
        if chiave not in MAP_KEYS:
            raise MapConfigError(
                f"{campo}.{chiave}", "chiave sconosciuta",
                hint=f"chiavi di una mappa: {', '.join(MAP_KEYS)}")

    tipo = grezza.get('type')
    if tipo is None:
        raise MapConfigError(
            f"{campo}.type", "manca il tipo della mappa",
            hint=f"tipi disponibili: {', '.join(MAP_TYPES)}")
    if not isinstance(tipo, str) or tipo not in MAP_KINDS:
        raise MapConfigError(
            f"{campo}.type", "tipo sconosciuto", value=tipo,
            hint=f"tipi disponibili: {', '.join(MAP_TYPES)}")
    kind = MAP_KINDS[tipo]

    if grezza.get('r') is None:
        basso, alto = kind.r_range
        raise MapConfigError(
            f"{campo}.r", "manca r, il parametro della mappa",
            hint=f"per {tipo}: da {basso:g} a {alto:g}")
    r = _finito(grezza['r'], f"{campo}.r")

    clock = grezza.get('clock', MAP_CLOCK_GRAIN)
    if clock != MAP_CLOCK_GRAIN or isinstance(clock, bool):
        raise MapConfigError(
            f"{campo}.clock", "clock non riconosciuto", value=clock,
            hint=f"`{MAP_CLOCK_GRAIN}`: un passo per grano")

    x0 = kind.x0
    if 'x0' in grezza:
        x0 = _finito(grezza['x0'], f"{campo}.x0")

    transient = grezza.get('transient', MAP_TRANSIENT_DEFAULT)
    if (not isinstance(transient, int) or isinstance(transient, bool)
            or transient < 0):
        raise MapConfigError(
            f"{campo}.transient",
            "atteso un intero non negativo: i passi scartati prima del "
            "primo grano", value=transient)

    return MapDefinition(name=nome, kind=kind, r=r, x0=x0,
                         transient=transient)


def parse_maps(raw) -> Tuple[MapDefinition, ...]:
    """Il blocco `maps:` in definizioni validate, nell'ordine dello YAML.

    Raises:
        MapConfigError: senza stream; lo aggiunge `MapSet.from_yaml`.
    """
    if not isinstance(raw, dict):
        raise MapConfigError(
            'maps', "maps e' un dizionario: nome della mappa -> mappa",
            value=raw, hint="es. maps: {m1: {type: logistic, r: 3.5}}")
    if not raw:
        raise MapConfigError(
            'maps', "nessuna mappa dichiarata",
            hint="es. maps: {m1: {type: logistic, r: 3.5}}; "
                 "se non servono, togli la chiave")
    return tuple(_definizione(nome, grezza) for nome, grezza in raw.items())


# =============================================================================
# STATO
# =============================================================================

def _scappata(x: float) -> bool:
    return not math.isfinite(x) or abs(x) > MAP_ESCAPE_LIMIT


class _GrainClockMap:
    """Una mappa a `clock: grain`: un passo per grano, uno stato per voce."""

    def __init__(self, definition: MapDefinition, stream_id: str):
        self._definition = definition
        self._stream_id = stream_id
        self._step = definition.kind.step
        self._initial: Optional[float] = None
        self._states: Dict[int, float] = {}
        self._escape_logged_at = -math.inf
        self._escape_logged = False

    def _stato_iniziale(self) -> float:
        """`x0` dopo il transitorio. Calcolato una volta: e' lo stesso per
        ogni voce, perche' la mappa e' deterministica."""
        if self._initial is None:
            d = self._definition
            x = d.x0
            for _ in range(d.transient):
                x = self._step(x, d.r)
                if _scappata(x):
                    x = d.x0
            self._initial = x
        return self._initial

    def advance(self, voice: int, time: float) -> None:
        d = self._definition
        x = self._states.get(voice)
        if x is None:
            x = self._stato_iniziale()
        x = self._step(x, d.r)
        if _scappata(x):
            x = d.x0
            self._segnala_fuga(time)
        self._states[voice] = x

    def value(self, voice: int, time: float) -> float:
        x = self._states.get(voice)
        return self._stato_iniziale() if x is None else x

    def _segnala_fuga(self, time: float) -> None:
        if abs(time - self._escape_logged_at) < MAP_ESCAPE_LOG_INTERVAL:
            return
        self._escape_logged_at = time
        is_first = not self._escape_logged
        self._escape_logged = True
        d = self._definition
        log_map_escape_warning(
            stream_id=self._stream_id,
            map_name=d.name,
            elapsed_time=time,
            r=d.r,
            x0=d.x0,
            interval=MAP_ESCAPE_LOG_INTERVAL,
            is_first=is_first,
        )


class MapSet:
    """Le mappe dichiarate da uno stream. Vuoto se lo stream non ne ha."""

    def __init__(self, definitions: Iterable[MapDefinition] = (),
                 stream_id: str = 'unknown'):
        self.definitions: Tuple[MapDefinition, ...] = tuple(definitions)
        self.stream_id = stream_id
        self._maps = {
            d.name: _GrainClockMap(d, stream_id) for d in self.definitions}
        self._per_grano = tuple(self._maps.values())
        self._voice = 0

    @classmethod
    def from_yaml(cls, raw, stream_id: Optional[str] = None) -> 'MapSet':
        """Costruisce l'insieme dal valore della chiave `maps:`.

        La chiave assente non passa di qui: e' `MapSet()`. Una chiave scritta
        e lasciata vuota si' — ed e' un errore, perche' una riga che qualcuno
        ha scritto e nessuno legge e' il default piu' muto possibile.

        Raises:
            MapConfigError: col path YAML del punto, e lo stream se e' dato.
        """
        try:
            definizioni = parse_maps(raw)
        except MapConfigError as err:
            err.stream_id = stream_id
            raise
        return cls(definizioni, stream_id=stream_id or 'unknown')

    @property
    def names(self) -> Tuple[str, ...]:
        """I nomi delle mappe, nell'ordine dello YAML."""
        return tuple(self._maps)

    @property
    def variables(self) -> Tuple[str, ...]:
        """I nomi che un'espressione di questo stream puo' leggere."""
        return self.names + (TIME_NAME,)

    def __len__(self) -> int:
        return len(self._maps)

    # -- chi le muove ---------------------------------------------------------

    def advance(self, voice: int, time: float) -> None:
        """Il giro di una voce comincia: le sue mappe a `clock: grain` fanno
        un passo, e da qui le letture sono le sue."""
        self._voice = voice
        for mappa in self._per_grano:
            mappa.advance(voice, time)

    def select(self, voice: int) -> None:
        """Da qui le letture sono di questa voce, senza muovere niente."""
        self._voice = voice

    # -- chi le legge ---------------------------------------------------------

    def value(self, name: str, time: float) -> float:
        """Il valore di una mappa per la voce di turno. Non la muove."""
        return self._maps[name].value(self._voice, time)

    def environment(self, names: Iterable[str], time: float) -> Dict[str, float]:
        """L'ambiente di un'espressione: i soli nomi che legge."""
        return {
            name: time if name == TIME_NAME else self.value(name, time)
            for name in names
        }
