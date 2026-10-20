# src/pge/controllers/voices_controller.py
"""
VoicesController - il blocco YAML `voices:` (issue #284).

Lo legge come `PointerController` legge `pointer:` e `PitchController`
`pitch:`: lo `Stream` gli passa il sotto-blocco e la config, e lui costruisce
il `VoiceManager`, i `Parameter` `num_voices` e `scatter` e l'unita'
dell'offset di pointer. Prima lo faceva lo `Stream`, ed era l'unico
sotto-blocco che leggeva per conto di un collaboratore; scriveva lo stato su
di se' invece di restituirlo, e una parte la rileggeva a ogni grano.

Dallo `Stream` il wiring leggeva tre valori — `duration`, `seed`,
`stream_id` — e stanno tutti in `config`: qui si leggono da li'
(`config.context.duration`, `config.seed`, `config.context.stream_id`).

Le quattro dimensioni del blocco sono un passo solo ripetuto su una tabella
(`_VOICE_AXES`, issue #186): le differenze vere stanno nei due hook
`_take_voice_pitch_keys` e `_take_voice_pointer_keys`. La decisione che ha
tracciato questo confine e' in `docs/explanation/stream-decomposition.md`
(#190).
"""
from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Optional

from pge.controllers.voice_manager import VoiceManager
from pge.core.stream_config import StreamConfig
from pge.envelopes.envelope import Envelope, create_scaled_envelope
from pge.parameters.parameter import Parameter
from pge.parameters.parameter_definitions import GRANULAR_PARAMETERS
from pge.parameters.parser import GranularParser
from pge.parameters.pitch_unit import make_pitch_unit
from pge.shared.exceptions import (
    ConfigError,
    InvalidFieldValueError,
    InvalidStrategyConfigError,
)
from pge.strategies.voice_onset_strategy import VoiceOnsetStrategyFactory
from pge.strategies.voice_pan_strategy import VoicePanStrategyFactory
from pge.strategies.voice_pitch_strategy import VoicePitchStrategyFactory, SEMITONE_LOCKED
from pge.strategies.voice_pointer_strategy import VoicePointerStrategyFactory


_STRATEGY_KWARG_HINT = (
    "un parametro di una voice strategy e' un numero, un nome o un envelope: "
    "una lista di breakpoint ([[t, v], ...]), un formato compatto, un BP group "
    "o un dict con `points`. Una lista vuota o di soli numeri, o un dict senza "
    "`points`, non e' nessuno dei tre."
)


def _parse_strategy_kwarg(value, duration: float, stream_time_mode: str = 'absolute',
                          field: Optional[str] = None):
    """Converte kwarg YAML strategy: str/int passthrough, envelope-like → Envelope.

    Gli envelope-like ereditano il `time_mode` dello stream (issue #144),
    esattamente come gli envelope diretti via GranularParser. In forma dict il
    `time_mode` locale sovrascrive quello dello stream; in forma compatta (lista)
    si applica il time_mode dello stream.

    `field` e' il path YAML del kwarg (`voices.pan.step`), che gli errori di
    forma dell'envelope nominano (issue #211).

    Una lista o un dict che envelope non e' si ferma qui, su `field` (issue
    #288). Nessun kwarg di strategy ne accetta uno — sono numeri, nomi o
    envelope; `progression` di `chord_progression`, l'unico strutturale, lo
    sottrae `_take_voice_pitch_keys` prima di questa conversione — e
    lasciarlo passare voleva dire uno Stream che si costruisce e un TypeError
    nudo al primo grano, quando `resolve_param` fa `float()` su una lista.
    """
    if isinstance(value, (str, int, float)):
        return value
    if Envelope.is_envelope_like(value):
        if isinstance(value, dict):
            tm = value.get('time_mode', stream_time_mode)
        else:
            tm = stream_time_mode
        if tm == 'normalized':
            return create_scaled_envelope(value, duration, 'normalized', field=field)
        return Envelope(value, field=field)
    if isinstance(value, (list, dict)):
        raise InvalidFieldValueError(
            field=field if field is not None else 'voices',
            value=value,
            hint=_STRATEGY_KWARG_HINT,
        )
    return value


@dataclass(frozen=True)
class _VoiceAxis:
    """
    Una dimensione del blocco `voices:`: una riga di
    `VoicesController._VOICE_AXES` (issue #186).

    Attributes:
        yaml_key: chiave del sotto-blocco dentro `voices:`.
        factory:  Factory della dimensione. `create(name, **kwargs)` ha la
                  stessa firma sulle quattro, qualunque registry ci sia dietro.
        slot:     kwarg di VoiceManager che riceve la strategy.
        take_block_keys: le differenze vere della dimensione, o None se non ne
                  ha. E' il *nome* di un metodo di VoicesController
                  `(name, kw) -> (strutturali, per_manager)`, che toglie da
                  `kw` cio' che il passo comune non deve vedere — le chiavi di
                  blocco, config della dimensione e non della strategy, e i
                  kwarg con la forma di un envelope che envelope non sono. Il
                  nome e non la funzione: la tabella sta nel corpo della
                  classe, e una funzione catturata li' verrebbe chiamata
                  scavalcando l'istanza — un override o un `patch.object` sul
                  controller non la raggiungerebbero.
    """
    yaml_key: str
    factory: type
    slot: str
    take_block_keys: Optional[str] = None


class VoicesController:
    """
    Costruisce le voci di uno stream dal blocco YAML `voices:`.

    YAML supportato:
        voices:
          num_voices: 4
          pitch:
            strategy: chord
            chord: "dom7"
          onset_offset:
            strategy: linear
            step: 0.05
          pointer:
            strategy: stochastic
            pointer_range: 0.1
          pan:
            strategy: range
            spread: 60.0

    - blocco assente (o vuoto) → una voce, `VoiceManager(max_voices=1)`
    - strategy stocastiche: identita' RNG iniettata nel kwarg `stream_id` —
      vale rng_id (issue #169): lo stream_id, o il rng_group quando la
      sequenza e' condivisa fra stream — e seed del run

    Attributes:
        voice_manager: il `VoiceManager` con le strategy delle dimensioni.
        num_voices: `Parameter` (supporta Envelope time-varying).
        scatter: `Parameter` (supporta Envelope time-varying).
        pointer_normalized: l'unita' dell'offset di pointer delle voci, dal
            flag `normalized:` del sotto-blocco `pointer:`. False (default) →
            secondi nel sample; True → frazione di `sample_dur_sec`. Lo legge
            `Stream._create_grain` a ogni grano.
    """

    def __init__(
        self,
        params: dict,                # 1. Dati specifici (blocco voices YAML)
        config: StreamConfig         # 2. Regole processo
    ):
        self._config = config

        # Il default va scritto prima di sapere se il blocco c'e': lo legge
        # `Stream._create_grain` a ogni grano, anche senza `voices:` o senza
        # il sotto-blocco `pointer:` (che lo scrive in _take_voice_pointer_keys).
        self.pointer_normalized = False

        if not params:
            # Senza blocco voices, valori di default (nessun parser necessario)
            self.num_voices = Parameter('num_voices', 1.0, GRANULAR_PARAMETERS['num_voices'])
            self.scatter = Parameter('scatter', 0.0, GRANULAR_PARAMETERS['scatter'])
            self.voice_manager = VoiceManager(max_voices=1)
            return

        parser = GranularParser(config)

        raw_num_voices = params.get('num_voices', 1)

        # Parsa num_voices come Parameter (supporta Envelope time-varying, incluso formato dict).
        self.num_voices = parser.parse_parameter(
            'num_voices', raw_num_voices, value_field='voices.num_voices')

        # Estrae max_voices per pre-computare tutti i VoiceConfig all'init.
        # Se num_voices è un Envelope, max_voices = picco dei breakpoints.
        param_val = self.num_voices.value
        if isinstance(param_val, Envelope):
            max_voices = ceil(max(bp[1] for bp in param_val.breakpoints))
        else:
            max_voices = ceil(param_val)
        self.scatter = parser.parse_parameter(
            'scatter', params.get('scatter', 0.0), value_field='voices.scatter')

        # Il ciclo e' sulla tabella, non sulle chiavi di `voices:`: l'ordine
        # delle dimensioni — e quindi quale errore arriva per primo quando
        # piu' sotto-blocchi sono sbagliati — non dipende da come e' scritto
        # lo YAML.
        manager_kwargs = {}
        for axis in self._VOICE_AXES:
            if axis.yaml_key not in params:
                continue
            strategy, for_manager = self._build_voice_strategy(axis, params[axis.yaml_key])
            manager_kwargs[axis.slot] = strategy
            manager_kwargs.update(for_manager)

        self.voice_manager = VoiceManager(max_voices=max_voices, **manager_kwargs)

    def _build_voice_strategy(self, axis: _VoiceAxis, block: dict):
        """
        Il passo comune alle quattro dimensioni: sotto-blocco YAML → strategy.

        Returns:
            (strategy, kwarg per VoiceManager oltre alla strategy)
        """
        config = self._config
        # Copia: il blocco resta quello scritto. Il Generator tiene lo stesso
        # dict in stream_data_map e la cache ne fa il fingerprint.
        kw = dict(block)
        name = kw.pop('strategy')
        structural, for_manager = {}, {}
        if axis.take_block_keys is not None:
            take = getattr(self, axis.take_block_keys)
            structural, for_manager = take(name, kw)
        # L'identita' RNG di una strategy stocastica la inietta il motore — lo
        # stream, o il suo rng_group, e il seed del run — e non e' un kwarg del
        # blocco: non passa per la conversione qui sotto, che legge i valori
        # scritti nel blocco e da #288 rifiuta una lista o un dict. Convertiti,
        # un rng_group o un seed non scalari diventavano un errore su
        # `voices.<asse>.stream_id` o `.seed`, chiavi che nel file non ci sono.
        # Uno `stream_id` o un `seed` scritti nel blocco restano sostituiti
        # dall'identita', come prima.
        identita = {}
        if name == 'stochastic':
            identita = {'stream_id': config.context.rng_id, 'seed': config.seed}
        # Gli errori di forma di un kwarg envelope nascono nel builder, dove lo
        # stream non si conosce: vanno attribuiti qui, come fa il parser coi
        # propri (issue #211).
        try:
            kw = {
                k: _parse_strategy_kwarg(
                    val, config.context.duration, config.time_mode,
                    field=f'voices.{axis.yaml_key}.{k}',
                )
                for k, val in kw.items() if k not in identita
            }
        except ConfigError as err:
            err.stream_id = config.context.stream_id
            raise
        kw.update(structural)
        kw.update(identita)
        return axis.factory.create(name, **kw), for_manager

    def _take_voice_pitch_keys(self, name: str, kw: dict):
        """
        Le differenze vere del pitch: l'hard break di `semitone_range`, la
        chiave di blocco `unit` (validata contro SEMITONE_LOCKED) e i kwarg
        strutturali di `chord_progression`.

        Returns:
            (kwarg strutturali, {'pitch_unit': ...} per VoiceManager)
        """
        config = self._config
        # Hard break: `semitone_range` rinominato in `pitch_range` (il valore è
        # letto nell'unità attiva, non in semitoni). Senza guard il kwarg ignoto
        # darebbe un TypeError grezzo dal costruttore della strategy.
        if 'semitone_range' in kw:
            err = InvalidStrategyConfigError(
                strategy_kind='voice_pitch',
                field='voices.pitch.semitone_range',
                value=kw['semitone_range'],
                hint=(
                    "`semitone_range` rinominato in `pitch_range` (stesso "
                    "valore, letto nell'unità attiva: semitones/cents/edo/ratio…)."
                ),
            )
            err.stream_id = config.context.stream_id
            raise err
        # `unit` è config del blocco, non kwarg della distribuzione: decide
        # come l'offset (numero puro) diventa ratio in Stream._create_grain.
        unit_spec = kw.pop('unit', None)
        # chord/chord_progression/spectral sono semitoni-locked
        # (SEMITONE_LOCKED): rifiuta unità ≠ semitones.
        if name in SEMITONE_LOCKED and unit_spec not in (None, 'semitones'):
            err = InvalidStrategyConfigError(
                strategy_kind='voice_pitch',
                field='voices.pitch.unit',
                value=unit_spec,
                hint=(
                    f"la strategia '{name}' è definita in semitoni: "
                    "ometti `unit` oppure usa 'semitones'."
                ),
            )
            err.stream_id = config.context.stream_id
            raise err
        pitch_unit = make_pitch_unit(unit_spec)
        # chord_progression: i kwarg strutturali NON sono envelope-like e
        # vanno sottratti alla conversione del passo comune. In particolare
        # `progression` (lista di [t, str]) verrebbe scambiata per envelope
        # da is_envelope_like → crash su evaluate.
        structural = {}
        if name == 'chord_progression':
            for key in ('progression', 'interp', 'voice_leading'):
                if key in kw:
                    structural[key] = kw.pop(key)
            # I tempi della progressione seguono il time_mode dello stream,
            # come gli envelope: normalized → 0..1 scalati sulla duration.
            if config.time_mode == 'normalized':
                structural['time_mode'] = 'normalized'
                structural['duration'] = config.context.duration
        return structural, {'pitch_unit': pitch_unit}

    def _take_voice_pointer_keys(self, name: str, kw: dict):
        """
        La differenza vera del pointer: la chiave di blocco `normalized`. La
        legge Stream._create_grain, quindi resta sul controller come
        `pointer_normalized` e non va a VoiceManager.
        """
        # Solo bool puro: niente coercion silenziosa (cfr. grain.reverse,
        # envelope_builder — il progetto valida i flag, non li forza).
        raw_normalized = kw.pop('normalized', False)
        if not isinstance(raw_normalized, bool):
            err = InvalidFieldValueError(
                field='voices.pointer.normalized',
                value=raw_normalized,
                hint="normalized accetta solo true/false (default: false).",
            )
            err.stream_id = self._config.context.stream_id
            raise err
        self.pointer_normalized = raw_normalized
        return {}, {}

    # Le quattro dimensioni del blocco `voices:` (issue #186), nell'ordine in
    # cui si valutano. Solo pitch e pointer hanno chiavi proprie; onset_offset
    # e pan sono il passo comune e basta.
    _VOICE_AXES = (
        _VoiceAxis('pitch',        VoicePitchStrategyFactory,   'pitch_strategy',
                   '_take_voice_pitch_keys'),
        _VoiceAxis('onset_offset', VoiceOnsetStrategyFactory,   'onset_strategy'),
        _VoiceAxis('pointer',      VoicePointerStrategyFactory, 'pointer_strategy',
                   '_take_voice_pointer_keys'),
        _VoiceAxis('pan',          VoicePanStrategyFactory,     'pan_strategy'),
    )
