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

Una mappa sa solo fare «un altro passo»: quando, lo dice lo YAML (issue #310).

| scrittura             | quando fa un passo                         | stato        |
|-----------------------|--------------------------------------------|--------------|
| `clock: grain`        | ogni volta che nasce un grano              | uno per voce |
| `clock: 8`            | 8 passi al secondo; il valore resta fermo  | nessuno: e'  |
|                       | fino al passo dopo                         | una funzione |
| `clock: [[0, 2], ..]` | il passo k cade dove l'integrale del clock | del tempo    |
|                       | vale k                                     |              |
| `iterate: 7`          | mai: a ogni lettura si riparte da `x0` e   | nessuno      |
|                       | si fanno 7 passi con l'`r` di quell'istante|              |

`r` puo' essere un envelope: si legge all'istante del passo (o della lettura,
in `iterate`), e segue il `time_mode` dello stream come ogni altro envelope.

Tre chiavi hanno un tetto, perche' contano dei passi e un passo costa: senza,
un numero grande scritto per sbaglio teneva fermo il render invece di dire
che cosa non va. `iterate` al piu' `MAP_ITERATE_MAX` (i passi a ogni
lettura), `transient` al piu' `MAP_TRANSIENT_MAX` (una volta per mappa), il
clock al piu' un passo per campione (`output_sr`).
"""
from __future__ import annotations

import math
import re
from array import array
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple, Union

from pge.envelopes.envelope import Envelope, create_scaled_envelope
from pge.expressions.expression import (
    CONSTANTS, FUNCTIONS, compile_expression,
)
from pge.maps.catalog import MAP_KINDS, MAP_TYPE_CUSTOM, MAP_TYPES, MapKind
from pge.shared.constants import DEFAULT_OUTPUT_SR
from pge.shared.exceptions import ConfigError, MapConfigError
from pge.shared.logger import log_map_escape_warning

#: Le chiavi di una mappa, come letterale (vedi MAP_TYPES). `x` e `y` sono le
#: equazioni di una mappa `type: custom`, `y0` lo stato iniziale della
#: seconda variabile di una mappa che ne ha due (issue #313).
MAP_KEYS = ('type', 'r', 'clock', 'iterate', 'x0', 'transient',
            'y0', 'x', 'y')

#: Le variabili che l'equazione di una mappa `custom` puo' leggere: lo stato
#: e il parametro. Sono i nomi riservati che una mappa non puo' prendere.
MAP_EQUATION_VARIABLES = ('x', 'y', 'r')

#: Lo stato iniziale di una mappa `custom` quando lo YAML non lo scrive. Non
#: zero: per molte equazioni (`r*x*(1-x)`, `sin(r*x)`) zero e' un punto
#: fisso, e la mappa non partirebbe.
MAP_CUSTOM_X0 = 0.1
MAP_CUSTOM_Y0 = 0.1

#: Il suffisso con cui un'espressione legge la seconda variabile: `m1.y`.
MAP_SECOND_VARIABLE = 'y'

#: `clock: grain`: un passo ogni volta che nasce un grano. E' il default.
MAP_CLOCK_GRAIN = 'grain'

#: I tre modi di avanzare (issue #310): per grano, a orologio, iterata.
MAP_MODE_GRAIN = 'grain'
MAP_MODE_CLOCK = 'clock'
MAP_MODE_ITERATE = 'iterate'

#: Passi scartati prima del primo grano, quando `transient` non e' scritto.
MAP_TRANSIENT_DEFAULT = 300

#: Il transitorio piu' lungo che si puo' scrivere. Si fa una volta per mappa,
#: e fin qui costa pochi millisecondi; e' piu' di trecento volte il default,
#: abbastanza per gli attrattori che si raggiungono piano (vicino a una
#: biforcazione). Oltre non c'e' un attrattore che lo chieda: c'e' un numero
#: scritto per sbaglio, che teneva fermo il caricamento per minuti.
MAP_TRANSIENT_MAX = 100_000

#: I passi piu' numerosi che `iterate` puo' fare a ogni lettura. E' il tetto
#: del «Banco del chirp», che pero' li' taglia in silenzio, e non e' solo un
#: limite di costo (si itera a ogni grano): a r = 4 la logistica perde un bit
#: dello stato iniziale a ogni passo, e dopo una cinquantina di passi
#: l'iterata non dipende piu' da r ma dagli arrotondamenti del float64.
MAP_ITERATE_MAX = 40

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
    """Una mappa come lo YAML la dichiara, gia' validata.

    `r` e `clock` sono un numero o un `Envelope` gia' costruito sui tempi
    dello stream. `mode` dice quale dei tre modi di avanzare vale: `clock` ha
    un valore solo nel modo a orologio, `iterate` solo nel suo.
    """
    name: str
    kind: MapKind
    r: Union[float, Envelope]
    x0: float
    transient: int
    mode: str = MAP_MODE_GRAIN
    clock: Union[float, Envelope, None] = None
    iterate: Optional[int] = None
    #: lo stato iniziale della seconda variabile (issue #313); 0 per una
    #: mappa che ne ha una sola, dove non entra nel passo.
    y0: float = 0.0

    @property
    def two_variables(self) -> bool:
        """True se la mappa ha una seconda variabile, leggibile come
        `<nome>.y`."""
        return self.kind.variables == 2

    def r_at(self, time: float) -> float:
        """`r` a un istante: quello del passo, o della lettura."""
        if isinstance(self.r, Envelope):
            return self.r.evaluate(time)
        return self.r


# =============================================================================
# PARSE
# =============================================================================

_CLOCK_HINT = (f"`{MAP_CLOCK_GRAIN}` (un passo per grano), oppure i passi al "
               "secondo: un numero positivo o un envelope, al piu' uno per "
               "campione")


def _finito(valore, campo: str) -> float:
    if not _numero(valore):
        raise MapConfigError(campo, "atteso un numero", value=valore)
    if not math.isfinite(valore):
        raise MapConfigError(campo, "atteso un numero finito", value=valore)
    return float(valore)


def _envelope(grezzo, campo: str, duration, time_mode: str) -> Envelope:
    """Un envelope dichiarato dentro una mappa, sui tempi dello stream."""
    return create_scaled_envelope(
        grezzo, duration if duration is not None else 1.0, time_mode,
        field=campo)


def _r(grezzo, campo: str, duration, time_mode: str):
    if isinstance(grezzo, (list, dict)):
        envelope = _envelope(grezzo, campo, duration, time_mode)
        for _, y in envelope.breakpoints:
            if not math.isfinite(y):
                raise MapConfigError(
                    campo, "atteso un envelope di numeri finiti", value=y)
        return envelope
    return _finito(grezzo, campo)


def _oltre_un_passo_per_campione(clock: float, output_sr: int, campo: str,
                                 dove: str = ""):
    """Il tetto del clock: un passo per campione, la risoluzione del motore.

    E' lo stesso tetto a cui arriva, a ogni grano, una mappa a
    `clock: grain` con l'attesa piu' corta che `grain.iot` ammette. Un passo
    piu' fitto nessun grano lo vede da solo, e costa come un passo vero: un
    `clock: 1e9` scritto per sbaglio teneva fermo il render.
    """
    if clock > output_sr:
        raise MapConfigError(
            campo, f"il clock e' al piu' un passo per campione: {output_sr} "
            f"passi al secondo{dove}", value=clock, hint=_CLOCK_HINT)


def _clock(grezzo, campo: str, duration, time_mode: str, output_sr: int):
    """`(modo, clock)`: `grain`, oppure i passi al secondo."""
    if grezzo == MAP_CLOCK_GRAIN and isinstance(grezzo, str):
        return MAP_MODE_GRAIN, None
    if isinstance(grezzo, (list, dict)):
        envelope = _envelope(grezzo, campo, duration, time_mode)
        for _, y in envelope.breakpoints:
            if not (math.isfinite(y) and y > 0):
                raise MapConfigError(
                    campo, "il clock dev'essere positivo e finito in ogni "
                    "punto dell'envelope", value=y, hint=_CLOCK_HINT)
            _oltre_un_passo_per_campione(
                y, output_sr, campo, dove=" in ogni punto dell'envelope")
        return MAP_MODE_CLOCK, envelope
    if _numero(grezzo):
        if not (math.isfinite(grezzo) and grezzo > 0):
            raise MapConfigError(
                campo, "il clock dev'essere positivo e finito", value=grezzo,
                hint=_CLOCK_HINT)
        _oltre_un_passo_per_campione(grezzo, output_sr, campo)
        return MAP_MODE_CLOCK, float(grezzo)
    raise MapConfigError(
        campo, "clock non riconosciuto", value=grezzo, hint=_CLOCK_HINT)


def _equazione(grezza, campo: str):
    """Un'equazione di una mappa `custom`, compilata: `env -> float`.

    Il linguaggio e' quello delle espressioni, con le variabili `x`, `y`,
    `r`. Qui il testo e' il valore di una chiave che vuol dire «equazione»,
    quindi le parentesi esterne non servono: `x: sin(r*x)*cos(x)`.

    Raises:
        MapConfigError: se non e' un testo (o un numero, l'equazione
            costante).
        ExpressionError: se il testo non e' un'espressione del linguaggio;
            col path `maps.<nome>.x`.
    """
    if _numero(grezza):
        grezza = repr(float(grezza))
    if not isinstance(grezza, str):
        raise MapConfigError(
            campo, "un'equazione e' un testo, nel linguaggio delle "
            "espressioni, con le variabili x, y, r", value=grezza,
            hint="es. x: sin(r*x)*cos(x)")
    return compile_expression(grezza, MAP_EQUATION_VARIABLES, field=campo)


def _custom_kind(grezza: dict, campo: str):
    """`(kind, legge_r)` di una mappa `type: custom` (issue #313): il passo
    e' quello che lo YAML scrive in `x:` (obbligatoria) e `y:` (opzionale).
    """
    if grezza.get('x') is None:
        raise MapConfigError(
            f"{campo}.x", "manca x, l'equazione della mappa",
            hint="con type: custom il passo si scrive: x: sin(r*x)*cos(x). "
                 "Variabili: x, y, r")
    fx = _equazione(grezza['x'], f"{campo}.x")
    fy = (_equazione(grezza['y'], f"{campo}.y")
          if grezza.get('y') is not None else None)
    if 'y' in grezza and fy is None:
        raise MapConfigError(
            f"{campo}.y", "y e' scritta ma vuota",
            hint="scrivi l'equazione della seconda variabile, o togli la "
                 "chiave")
    letti = set(fx.names) | set(fy.names if fy else ())

    if fy is None:
        if 'y' in fx.names:
            raise MapConfigError(
                f"{campo}.x", "l'equazione legge y, ma la mappa non ha una "
                "seconda variabile", value=grezza['x'],
                hint="aggiungi l'equazione y: (es. y: 0.3*x), o togli y "
                     "da x:")

        def step(x, r):
            return fx({'x': x, 'y': 0.0, 'r': r})
        kind = MapKind(name=MAP_TYPE_CUSTOM, step=step, x0=MAP_CUSTOM_X0,
                       r_range=None, value_range=None)
    else:
        def step_xy(x, y, r):
            # I due aggiornamenti usano la coppia di prima.
            env = {'x': x, 'y': y, 'r': r}
            return fx(env), fy(env)
        kind = MapKind(name=MAP_TYPE_CUSTOM, step=None, x0=MAP_CUSTOM_X0,
                       r_range=None, value_range=None, variables=2,
                       step_xy=step_xy, y0=MAP_CUSTOM_Y0)
    return kind, 'r' in letti


def _definizione(nome, grezza, duration, time_mode: str,
                 output_sr: int) -> MapDefinition:
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

    disponibili = ', '.join(MAP_TYPES + (MAP_TYPE_CUSTOM,))
    tipo = grezza.get('type')
    if tipo is None:
        raise MapConfigError(
            f"{campo}.type", "manca il tipo della mappa",
            hint=f"tipi disponibili: {disponibili}")
    if tipo == MAP_TYPE_CUSTOM and isinstance(tipo, str):
        kind, legge_r = _custom_kind(grezza, campo)
    elif not isinstance(tipo, str) or tipo not in MAP_KINDS:
        raise MapConfigError(
            f"{campo}.type", "tipo sconosciuto", value=tipo,
            hint=f"tipi disponibili: {disponibili}")
    else:
        kind, legge_r = MAP_KINDS[tipo], True
        # Un tipo di catalogo ha gia' la sua equazione: con accanto un `x:`
        # non si capirebbe quale delle due vale.
        for chiave in ('x', 'y'):
            if chiave in grezza:
                raise MapConfigError(
                    f"{campo}.{chiave}",
                    f"{chiave}: si scrive solo con type: {MAP_TYPE_CUSTOM}: "
                    f"{tipo} ha gia' la sua equazione, e non si capirebbe "
                    "quale delle due vale", value=grezza[chiave],
                    hint=f"togli {chiave}:, oppure scrivi type: "
                         f"{MAP_TYPE_CUSTOM}")

    if grezza.get('r') is None:
        if legge_r:
            hint = ("l'equazione lo legge: scrivi r, un numero o un envelope"
                    if kind.r_range is None else
                    f"per {tipo}: da {kind.r_range[0]:g} a "
                    f"{kind.r_range[1]:g}")
            raise MapConfigError(
                f"{campo}.r", "manca r, il parametro della mappa", hint=hint)
        # Un'equazione che non legge `r` non ne ha bisogno.
        r = 0.0
    else:
        r = _r(grezza['r'], f"{campo}.r", duration, time_mode)

    x0 = kind.x0
    if 'x0' in grezza:
        x0 = _finito(grezza['x0'], f"{campo}.x0")

    y0 = kind.y0
    if 'y0' in grezza:
        if kind.variables != 2:
            raise MapConfigError(
                f"{campo}.y0", "la mappa ha una variabile sola: y0 non "
                "entra nel passo", value=grezza['y0'],
                hint="togli y0; lo stato iniziale e' x0")
        y0 = _finito(grezza['y0'], f"{campo}.y0")

    # `iterate` sta al posto di `clock`, e non e' un clock: insieme dicono
    # due cose diverse su quando la mappa si muove. Un errore, non una
    # priorita'.
    if 'iterate' in grezza:
        if 'clock' in grezza:
            raise MapConfigError(
                campo, "clock e iterate insieme: una mappa o avanza con un "
                "clock, o si rilegge da x0 a ogni lettura (iterate)",
                hint="tieni una delle due chiavi")
        n = grezza['iterate']
        if not isinstance(n, int) or isinstance(n, bool) or n < 1:
            raise MapConfigError(
                f"{campo}.iterate",
                "atteso un intero positivo: i passi fatti da x0 a ogni "
                "lettura", value=n)
        if n > MAP_ITERATE_MAX:
            raise MapConfigError(
                f"{campo}.iterate",
                f"al piu' {MAP_ITERATE_MAX} passi a ogni lettura: oltre, "
                "l'iterata non dipende piu' da r ma dagli arrotondamenti, e "
                "si rifa' a ogni grano", value=n,
                hint=f"da 1 a {MAP_ITERATE_MAX}")
        if 'transient' in grezza:
            raise MapConfigError(
                f"{campo}.transient",
                "con iterate non c'e' un transitorio: a ogni lettura si "
                "riparte da x0", value=grezza['transient'],
                hint="togli transient, oppure usa clock al posto di iterate")
        return MapDefinition(name=nome, kind=kind, r=r, x0=x0, transient=0,
                             mode=MAP_MODE_ITERATE, iterate=n, y0=y0)

    mode, clock = _clock(grezza.get('clock', MAP_CLOCK_GRAIN),
                         f"{campo}.clock", duration, time_mode, output_sr)

    transient = grezza.get('transient', MAP_TRANSIENT_DEFAULT)
    if (not isinstance(transient, int) or isinstance(transient, bool)
            or transient < 0):
        raise MapConfigError(
            f"{campo}.transient",
            "atteso un intero non negativo: i passi scartati prima del "
            "primo grano", value=transient)
    if transient > MAP_TRANSIENT_MAX:
        raise MapConfigError(
            f"{campo}.transient",
            f"al piu' {MAP_TRANSIENT_MAX} passi scartati: bastano per ogni "
            "attrattore, anche per quelli che si raggiungono piano",
            value=transient, hint=f"da 0 a {MAP_TRANSIENT_MAX}")

    return MapDefinition(name=nome, kind=kind, r=r, x0=x0,
                         transient=transient, mode=mode, clock=clock, y0=y0)


def parse_maps(raw, duration: Optional[float] = None,
               time_mode: str = 'absolute',
               output_sr: Optional[int] = None) -> Tuple[MapDefinition, ...]:
    """Il blocco `maps:` in definizioni validate, nell'ordine dello YAML.

    `duration` e `time_mode` sono quelli dello stream: servono agli envelope
    di `r` e di `clock`, che seguono il `time_mode` come ogni altro.
    `output_sr` da' il tetto del clock, un passo per campione; None e' il
    sample rate di default del motore.

    Raises:
        MapConfigError, o il ConfigError di un envelope malformato: senza
        stream, che aggiunge `MapSet.from_yaml`.
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
    sr = DEFAULT_OUTPUT_SR if output_sr is None else output_sr
    return tuple(_definizione(nome, grezza, duration, time_mode, sr)
                 for nome, grezza in raw.items())


# =============================================================================
# STATO
# =============================================================================

def _scappata(x: float) -> bool:
    return not math.isfinite(x) or abs(x) > MAP_ESCAPE_LIMIT


class _Map:
    """Cio' che i tre modi di avanzare hanno in comune: il passo con la rete
    per la mappa che scappa, e lo stato dopo il transitorio.

    Lo stato e' una coppia `(x, y)` (issue #313): una mappa a una variabile
    porta una `y` che il suo passo non tocca, e ha lo stesso giro di una che
    ne ha due.
    """

    #: True se la mappa va mossa in testa al giro di una voce.
    per_grano = False

    def __init__(self, definition: MapDefinition, stream_id: str):
        self._definition = definition
        self._stream_id = stream_id
        self._advance = definition.kind.advance
        self._start: Tuple[float, float] = (definition.x0, definition.y0)
        self._initial: Optional[Tuple[float, float]] = None
        self._escape_logged_at = -math.inf
        self._escape_logged = False

    def _passo(self, stato: Tuple[float, float], r: float,
               time: Optional[float]) -> Tuple[float, float]:
        """Un passo. Se la mappa scappa — una delle due variabili — riparte
        dallo stato iniziale, e lo scrive (non durante il transitorio,
        `time` None: e' un fatto di prima del primo grano, e se continua lo
        dira' il primo passo vero)."""
        x, y = self._advance(stato[0], stato[1], r)
        if _scappata(x) or _scappata(y):
            if time is not None:
                self._segnala_fuga(time, r)
            return self._start
        return x, y

    def _stato_iniziale(self) -> Tuple[float, float]:
        """Lo stato iniziale dopo il transitorio, fatto a `r(0)`. Calcolato
        una volta: e' lo stesso per ogni voce, perche' la mappa e'
        deterministica."""
        if self._initial is None:
            d = self._definition
            stato, r = self._start, d.r_at(0.0)
            for _ in range(d.transient):
                stato = self._passo(stato, r, None)
            self._initial = stato
        return self._initial

    def _segnala_fuga(self, time: float, r: float) -> None:
        if abs(time - self._escape_logged_at) < MAP_ESCAPE_LOG_INTERVAL:
            return
        self._escape_logged_at = time
        is_first = not self._escape_logged
        self._escape_logged = True
        log_map_escape_warning(
            stream_id=self._stream_id,
            map_name=self._definition.name,
            elapsed_time=time,
            r=r,
            x0=self._definition.x0,
            interval=MAP_ESCAPE_LOG_INTERVAL,
            is_first=is_first,
        )

    def advance(self, voice: int, time: float) -> None:
        """Il giro di una voce comincia. Solo `clock: grain` si muove."""

    def state(self, voice: int, time: float) -> Tuple[float, float]:
        """La coppia `(x, y)` che la voce legge a quell'istante."""
        raise NotImplementedError

    def value(self, voice: int, time: float) -> float:
        return self.state(voice, time)[0]

    def step_times(self, until: float) -> Optional[List[float]]:
        """Gli istanti dei passi in [0, until), o None se la mappa non ha
        passi nel tempo."""
        return None


class _GrainClockMap(_Map):
    """`clock: grain`: un passo per grano, uno stato per voce."""

    per_grano = True

    def __init__(self, definition: MapDefinition, stream_id: str):
        super().__init__(definition, stream_id)
        self._states: Dict[int, Tuple[float, float]] = {}

    def advance(self, voice: int, time: float) -> None:
        stato = self._states.get(voice)
        if stato is None:
            stato = self._stato_iniziale()
        self._states[voice] = self._passo(
            stato, self._definition.r_at(time), time)

    def state(self, voice: int, time: float) -> Tuple[float, float]:
        stato = self._states.get(voice)
        return self._stato_iniziale() if stato is None else stato


#: Tolleranza sul conto dei passi: a un istante che e' esattamente quello di
#: un passo, l'integrale del clock puo' cadere un soffio sotto l'intero.
_CLOCK_EPSILON = 1e-9


class _TimeClockMap(_Map):
    """`clock:` numero o envelope: una funzione del tempo.

    Il passo k cade all'istante t_k in cui l'integrale del clock vale k (il
    primo, k = 0, a t = 0), e si fa con `r(t_k)`. Fra un passo e l'altro il
    valore resta fermo. Non c'e' uno stato per voce: i passi si calcolano in
    ordine, una volta, e si tengono; una lettura a un tempo qualunque — anche
    che torna indietro, come succede con piu' voci e `scatter` — cerca il suo
    passo fra quelli gia' fatti.
    """

    def __init__(self, definition: MapDefinition, stream_id: str):
        super().__init__(definition, stream_id)
        self._clock = definition.clock
        self._costante = not isinstance(self._clock, Envelope)
        # In `array('d')`: otto byte a passo invece di una trentina. Al tetto
        # del clock, un passo per campione, uno stream lungo ne fa milioni.
        # La seconda variabile si tiene solo per le mappe che ne hanno una.
        self._times = array('d')
        self._values = array('d')
        self._values_y = array('d') if definition.two_variables else None
        if not self._costante:
            self._minimo = min(y for _, y in self._clock.breakpoints)

    def _integrale(self, time: float) -> float:
        if time <= 0:
            return 0.0
        if self._costante:
            return self._clock * time
        return self._clock.integrate(0.0, time)

    def _tempo_del_passo(self, k: int) -> float:
        """L'istante in cui l'integrale del clock vale k."""
        if k == 0:
            return 0.0
        if self._costante:
            return k / self._clock
        # L'integrale di un clock positivo cresce: si cerca dopo il passo
        # precedente, con Newton (la derivata e' il clock) tenuto dentro una
        # forchetta, cosi' una cubica che esce dai suoi breakpoint non lo
        # manda fuori strada.
        lo = self._times[k - 1]
        hi = lo + 1.0 / self._minimo
        for _ in range(64):
            if self._integrale(hi) >= k:
                break
            hi = lo + 2.0 * (hi - lo)
        t = min(hi, lo + (k - self._integrale(lo))
                / max(self._clock.evaluate(lo), self._minimo))
        for _ in range(80):
            scarto = self._integrale(t) - k
            if abs(scarto) < 1e-11:
                break
            if scarto > 0:
                hi = t
            else:
                lo = t
            passo = self._clock.evaluate(t)
            nuovo = t - scarto / passo if passo > 0 else lo
            if not lo < nuovo < hi:
                nuovo = 0.5 * (lo + hi)
            if hi - lo < 1e-13:
                break
            t = nuovo
        return t

    def _stato_al_passo(self, k: int) -> Tuple[float, float]:
        y = self._values_y[k] if self._values_y is not None else 0.0
        return self._values[k], y

    def _fino_a(self, k: int) -> None:
        d = self._definition
        while len(self._values) <= k:
            j = len(self._values)
            t = self._tempo_del_passo(j)
            stato = self._stato_al_passo(j - 1) if j else self._stato_iniziale()
            x, y = self._passo(stato, d.r_at(t), t)
            self._times.append(t)
            self._values.append(x)
            if self._values_y is not None:
                self._values_y.append(y)

    def state(self, voice: int, time: float) -> Tuple[float, float]:
        k = int(math.floor(self._integrale(time) + _CLOCK_EPSILON))
        self._fino_a(k)
        return self._stato_al_passo(k)

    def value(self, voice: int, time: float) -> float:
        k = int(math.floor(self._integrale(time) + _CLOCK_EPSILON))
        self._fino_a(k)
        return self._values[k]

    def step_times(self, until: float) -> List[float]:
        k = 0
        while True:
            self._fino_a(k)
            if self._times[k] >= until - _CLOCK_EPSILON:
                return list(self._times[:k])
            k += 1


class _IteratedMap(_Map):
    """`iterate: n`, il modo alla Di Scipio: nessuno stato.

    A ogni lettura si riparte da `x0` e si fanno n passi con l'`r` di
    quell'istante: il valore e' l'n-esima iterata della stessa funzione, e a
    disegnare la curva e' il movimento di `r`. Con `r` fermo il valore e'
    fermo. Dopo una fuga non si itera oltre: il valore e' `x0`.
    """

    def __init__(self, definition: MapDefinition, stream_id: str):
        super().__init__(definition, stream_id)
        self._last_time: Optional[float] = None
        self._last_state: Tuple[float, float] = self._start

    def state(self, voice: int, time: float) -> Tuple[float, float]:
        # Piu' parametri dello stesso grano la leggono allo stesso istante.
        if time == self._last_time:
            return self._last_state
        d = self._definition
        r = d.r_at(time)
        stato = self._start
        for _ in range(d.iterate):
            x, y = self._advance(stato[0], stato[1], r)
            if _scappata(x) or _scappata(y):
                stato = self._start
                self._segnala_fuga(time, r)
                break
            stato = (x, y)
        self._last_time, self._last_state = time, stato
        return stato


_MODI = {
    MAP_MODE_GRAIN: _GrainClockMap,
    MAP_MODE_CLOCK: _TimeClockMap,
    MAP_MODE_ITERATE: _IteratedMap,
}


class MapSet:
    """Le mappe dichiarate da uno stream. Vuoto se lo stream non ne ha."""

    def __init__(self, definitions: Iterable[MapDefinition] = (),
                 stream_id: str = 'unknown'):
        self.definitions: Tuple[MapDefinition, ...] = tuple(definitions)
        self.stream_id = stream_id
        self._maps = {
            d.name: _MODI[d.mode](d, stream_id) for d in self.definitions}
        self._per_grano = tuple(
            m for m in self._maps.values() if m.per_grano)
        self._voice = 0

    @classmethod
    def from_yaml(cls, raw, stream_id: Optional[str] = None,
                  duration: Optional[float] = None,
                  time_mode: str = 'absolute',
                  output_sr: Optional[int] = None) -> 'MapSet':
        """Costruisce l'insieme dal valore della chiave `maps:`.

        La chiave assente non passa di qui: e' `MapSet()`. Una chiave scritta
        e lasciata vuota si' — ed e' un errore, perche' una riga che qualcuno
        ha scritto e nessuno legge e' il default piu' muto possibile.

        `duration` e `time_mode` sono quelli dello stream, per gli envelope
        di `r` e di `clock` (issue #310); `output_sr` e' il suo sample rate,
        che da' il tetto del clock.

        Raises:
            MapConfigError: col path YAML del punto, e lo stream se e' dato.
            ConfigError: un envelope malformato, con lo stesso contesto.
        """
        try:
            definizioni = parse_maps(raw, duration=duration,
                                     time_mode=time_mode,
                                     output_sr=output_sr)
        except ConfigError as err:
            err.stream_id = stream_id
            raise
        return cls(definizioni, stream_id=stream_id or 'unknown')

    @property
    def names(self) -> Tuple[str, ...]:
        """I nomi delle mappe, nell'ordine dello YAML."""
        return tuple(self._maps)

    @property
    def variables(self) -> Tuple[str, ...]:
        """I nomi che un'espressione di questo stream puo' leggere: le
        mappe, la seconda variabile di quelle che ne hanno due (`m1.y`,
        issue #313), e `t`."""
        nomi = []
        for d in self.definitions:
            nomi.append(d.name)
            if d.two_variables:
                nomi.append(f"{d.name}.{MAP_SECOND_VARIABLE}")
        return tuple(nomi) + (TIME_NAME,)

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

    def step_times(self, name: str, until: float) -> Optional[List[float]]:
        """Gli istanti in [0, until) in cui una mappa a orologio fa un passo.

        None per una mappa che non ha passi nel tempo: a `clock: grain`
        dipendono dai grani, in `iterate` non ci sono.
        """
        return self._maps[name].step_times(until)

    def state(self, name: str, time: float) -> Tuple[float, float]:
        """La coppia `(x, y)` di una mappa per la voce di turno. Per una
        mappa a una variabile `y` non vuol dire niente."""
        return self._maps[name].state(self._voice, time)

    def environment(self, names: Iterable[str], time: float) -> Dict[str, float]:
        """L'ambiente di un'espressione: i soli nomi che legge."""
        ambiente = {}
        for name in names:
            if name == TIME_NAME:
                ambiente[name] = time
                continue
            mappa, _, seconda = name.partition('.')
            if seconda:
                ambiente[name] = self.state(mappa, time)[1]
            else:
                ambiente[name] = self.value(mappa, time)
        return ambiente
