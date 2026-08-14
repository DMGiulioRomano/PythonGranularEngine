# src/stream.py
"""
Stream - Orchestratore per la sintesi granulare.

Fase 6 del refactoring: questa classe coordina i controller specializzati:
- ParameterEvaluator: parsing e validazione parametri
- PointerController: posizionamento testina con loop e jitter
- PitchController: trasposizione (semitoni o ratio)
- DensityController: densità e distribuzione temporale
- VoiceManager: voci multiple con offset pitch/pointer

Mantiene backward compatibility con Generator e ScoreVisualizer.
Ispirato al DMX-1000 di Barry Truax (1988).
"""
from __future__ import annotations

import random
from math import ceil, floor, log10
from typing import List, Optional, Union

from pge.core.grain import Grain
from pge.envelopes.envelope import Envelope, create_scaled_envelope, scale_raw_param_values
from pge.controllers.window_controller import WindowController
from pge.controllers.pointer_controller import PointerController
from pge.controllers.pitch_controller import PitchController
from pge.controllers.density_controller import DensityController
from pge.shared.constants import SECONDS_PER_MILLISECOND
from pge.shared.utils import get_sample_duration
from pge.shared.exceptions import (
    InvalidFieldValueError,
    InvalidStrategyConfigError,
    MissingFieldError,
    SampleNotFoundError,
)
from pge.parameters.parameter_schema import STREAM_PARAMETER_SCHEMA
from pge.parameters.parameter_orchestrator import ParameterOrchestrator
from pge.core.stream_config import StreamConfig, StreamContext, resolve_stream_duration
from pge.controllers.voice_manager import VoiceManager, VoiceConfig
from pge.parameters.pitch_unit import make_pitch_unit
from pge.strategies.voice_pitch_strategy import VoicePitchStrategyFactory, SEMITONE_LOCKED
from pge.strategies.voice_onset_strategy import VoiceOnsetStrategyFactory
from pge.strategies.voice_pointer_strategy import VoicePointerStrategyFactory
from pge.strategies.voice_pan_strategy import VoicePanStrategyFactory
from pge.strategies.grain_clip_strategy import GrainClipStrategyFactory, OverflowMarginClipStrategy
from pge.strategies.strategie import nominal_value
from dataclasses import fields, MISSING as dataclass_MISSING


# Unita' di misura ammesse per grain.duration / grain.duration_range.
# 'seconds' e' il default storico; 'samples' esprime i valori in campioni
# alla frequenza di output del motore (StreamContext.output_sr);
# 'milliseconds' e' la scala comoda per la grana udibile (1-1000 ms) e usa un
# fattore fisso, indipendente dal sample rate.
GRAIN_DURATION_UNITS = ('seconds', 'samples', 'milliseconds')

# Etichette per i messaggi d'errore: unita' -> nome dei valori attesi.
_GRAIN_DURATION_UNIT_LABELS = {
    'samples': 'campioni',
    'milliseconds': 'millisecondi',
}


def _parse_strategy_kwarg(value, duration: float, stream_time_mode: str = 'absolute'):
    """Converte kwarg YAML strategy: str/int passthrough, envelope-like → Envelope.

    Gli envelope-like ereditano il `time_mode` dello stream (issue #144),
    esattamente come gli envelope diretti via GranularParser. In forma dict il
    `time_mode` locale sovrascrive quello dello stream; in forma compatta (lista)
    si applica il time_mode dello stream.
    """
    if isinstance(value, (str, int, float)):
        return value
    if Envelope.is_envelope_like(value):
        if isinstance(value, dict):
            tm = value.get('time_mode', stream_time_mode)
        else:
            tm = stream_time_mode
        if tm == 'normalized':
            return create_scaled_envelope(value, duration, 'normalized')
        return Envelope(value)
    return value


class Stream:
    """
    Orchestratore per uno stream di sintesi granulare.
    
    Coordina i controller specializzati e genera la lista di grani.
    Mantiene compatibilità con Generator e ScoreVisualizer.
    
    Attributes:
        voices: List[List[Grain]] - grani organizzati per voce
        grains: List[Grain] - lista flattened (backward compatibility)
    """
    
    def __init__(self, params: dict, seed=None, samples_dir=None):
        """
        Inizializza lo stream dai parametri YAML.

        Args:
            params: dizionario parametri dallo YAML
            seed: seed effettivo del run (issue #81/#154): YAML top-level o
                  session seed del Generator. Propagato alle voice strategy
                  stocastiche e, via StreamConfig, agli RNG per-componente
                  (parameter/gate/iot/window/detune). None (default) →
                  comportamento legacy (hash() per-voce, random globale
                  per i componenti).
            samples_dir: directory dei sample audio (Fase 2 refactor
                  library/CLI). None (default) → fallback sul globale
                  PATHSAMPLES (comportamento legacy).
        """
        # Seed di riproducibilità: iniettato nelle strategy stocastiche in
        # _init_voice_manager e in StreamConfig per gli RNG per-componente.
        self.seed = seed
        # Directory sample iniettata: usata nei due call-site di
        # get_sample_duration (qui e in _init_stream_context).
        self.samples_dir = samples_dir
        # === 3. CONFIGURATION ===
        sample = params.get('sample')
        stream_id = params.get('stream_id', 'unknown')
        if not sample:
            err = MissingFieldError(
                field='sample',
                hint="specificare il nome del file wav (es. sample: mio_file.wav)",
            )
            err.stream_id = stream_id
            raise err
        try:
            sample_dur = get_sample_duration(sample, base_path=samples_dir)
        except SampleNotFoundError as err:
            err.stream_id = stream_id
            raise
        self._check_required_context_fields(params, stream_id)
        config = StreamConfig.from_yaml(
            params,
            StreamContext.from_yaml(params, sample_dur_sec=sample_dur),
            seed=seed,
        )
        self._init_stream_context(params)
        # === 3.5. UNITA' DI MISURA DURATA GRANO ===
        # Da qui in poi grain.duration/duration_range sono in secondi,
        # qualunque sia l'unita' dichiarata nello YAML.
        params = self._pre_normalize_grain_params(params, config.context.output_sr)
        # === 4. PARAMETRI SPECIALI ===
        self._init_grain_reverse(params)
        # === 5. PARAMETRI DIRETTI (riceve config) ===
        self._init_stream_parameters(params, config)
        # === 6. CONTROLLER (riceve config) ===
        self._init_controllers(params, config)
        # === 7. VOICE MANAGER ===
        self._init_voice_manager(params, config)
        # === 7.5. GRAIN CLIP STRATEGY ===
        self._clip_strategy = GrainClipStrategyFactory.create(
            config.clip_strategy,
            margin=config.clip_margin,
        )
        # === 8. RIFERIMENTI CSOUND (assegnati da Generator) ===
        self.sample_table_num: Optional[int] = None
        self.envelope_table_num: Optional[int] = None
        # === 9. STATO ===
        # Generazione lazy dei grani (issue #117): i backing field restano vuoti
        # finche' qualcuno non legge le property voices/grains, che innescano
        # generate_grains() al primo accesso. Cosi' il Generator non genera i
        # grani per gli stream cache-clean (il renderer short-circuita su
        # is_dirty prima di leggere .voices), risparmiando il costo dominante.
        self._voices: List[List[Grain]] = []
        self._grains: List[Grain] = []  # backward compatibility (flat)
        self.generated = False

    @staticmethod
    def _required_context_fields() -> set:
        """Campi StreamContext che il YAML deve fornire: quelli senza default.

        Esclusi, pur non avendo un default nel dataclass:
        - sample_dur_sec: derivato dal file audio, mai dal YAML;
        - duration: se assente vale la durata del sample (issue #205), risolta
          da resolve_stream_duration invece che pretesa dallo YAML.
        """
        return {
            field.name for field in fields(StreamContext)
            if field.name not in ('sample_dur_sec', 'duration')
            and field.default is dataclass_MISSING
            and field.default_factory is dataclass_MISSING
        }

    def _check_required_context_fields(self, params, stream_id):
        """Verifica campi obbligatori StreamContext prima di StreamConfig.from_yaml."""
        missing = self._required_context_fields() - set(params.keys())
        if missing:
            missing_list = sorted(missing)
            err = MissingFieldError(fields=missing_list)
            err.stream_id = stream_id
            raise err

    def _init_stream_context(self, params):
        self._check_required_context_fields(params, params.get('stream_id', 'unknown'))
        for key in self._required_context_fields():
            setattr(self, key, params[key])
        # getattr: il metodo e' esercitato nei test anche su istanze create
        # con object.__new__ (bypass di __init__), dove samples_dir manca.
        self.sample_dur_sec = get_sample_duration(
            self.sample, base_path=getattr(self, 'samples_dir', None))
        # duration e' fuori dai campi obbligatori (issue #205): il setattr sopra
        # non la scrive piu', va risolta qui con la stessa regola di
        # StreamContext.from_yaml. Senza questa riga self.duration non esiste e
        # la prima generazione di grani solleva AttributeError.
        self.duration = resolve_stream_duration(params, self.sample_dur_sec)

    def _init_stream_parameters(self, params: dict, config: StreamConfig) -> None:
        """
        Inizializza parametri diretti di Stream usando ParameterOrchestrator.

        Design Pattern: Data-Driven Configuration
        - Lo schema STREAM_PARAMETER_SCHEMA definisce COSA caricare
        - ParameterOrchestrator sa COME crearlo
        - Stream riceve i Parameter già pronti
        """
        _orchestrator = ParameterOrchestrator(config=config)

        # 3. Crea tutti i parametri
        parameters = _orchestrator.create_all_parameters(
            params,
            schema=STREAM_PARAMETER_SCHEMA
        )
        
        # 4. Assegna come attributi
        for name, param in parameters.items():
            setattr(self, name, param)

    # =========================================================================
    # INIZIALIZZAZIONE CONTROLLER
    # =========================================================================
    
    def _init_controllers(self, params: dict, config: StreamConfig) -> None:
        """Inizializza tutti i controller con i loro parametri."""
        # POINTER CONTROLLER
        self._pointer = PointerController(
            params=params.get('pointer', {}),
            config=config
        )
        
        # PITCH CONTROLLER
        self._pitch = PitchController(
            params=params.get('pitch', {}),
            config=config
            )
        
        # DENSITY CONTROLLER
        self._density = DensityController(
            params=params,
            config=config
        )

        self._window_controller = WindowController(
            params=params.get('grain', {}),
            config=config
        )    
            
    def _init_voice_manager(self, params: dict, config: StreamConfig) -> None:
        """
        Costruisce VoiceManager dal blocco YAML 'voices:'.

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
                strategy: linear
                spread: 60.0

        - voices assente → VoiceManager(max_voices=1)
        - strategy stochastiche: identità RNG iniettata automaticamente nel
          kwarg `stream_id` — vale rng_id (issue #169): lo stream_id, o il
          rng_group quando la sequenza è condivisa fra stream
        - spread estratto dal blocco pan
        """
        from pge.parameters.parameter import Parameter
        from pge.parameters.parameter_definitions import GRANULAR_PARAMETERS

        # Modalità unità del voice pointer offset:
        #   False (default) → offset in secondi nel sample
        #   True            → offset normalizzato (frazione di sample_dur_sec)
        # Impostato dal flag `normalized:` nel blocco `pointer:` (vedi sotto).
        self._voice_pointer_normalized = False

        v = params.get('voices', {})
        if not v:
            # Senza blocco voices, valori di default (nessun config necessario)
            self._num_voices = Parameter('num_voices', 1.0, GRANULAR_PARAMETERS['num_voices'])
            self._scatter = Parameter('scatter', 0.0, GRANULAR_PARAMETERS['scatter'])
            self._voice_manager = VoiceManager(max_voices=1)
            return

        from pge.parameters.parser import GranularParser
        parser = GranularParser(config)

        raw_num_voices = v.get('num_voices', 1)

        # Parsa num_voices come Parameter (supporta Envelope time-varying, incluso formato dict).
        self._num_voices = parser.parse_parameter('num_voices', raw_num_voices)

        # Estrae max_voices per pre-computare tutti i VoiceConfig all'init.
        # Se num_voices è un Envelope, max_voices = picco dei breakpoints.
        param_val = self._num_voices.value
        if isinstance(param_val, Envelope):
            max_voices = ceil(max(bp[1] for bp in param_val.breakpoints))
        else:
            max_voices = ceil(param_val)
        self._scatter = parser.parse_parameter('scatter', v.get('scatter', 0.0))

        # --- PITCH ---
        pitch_strategy = None
        pitch_unit = None
        if 'pitch' in v:
            kw = dict(v['pitch'])
            name = kw.pop('strategy')
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
                err.stream_id = self.stream_id
                raise err
            # `unit` è config del blocco, non kwarg della distribuzione: decide
            # come l'offset (numero puro) diventa ratio in _create_grain.
            unit_spec = kw.pop('unit', None)
            # chord/spectral sono semitoni-locked: rifiuta unità ≠ semitones.
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
                err.stream_id = self.stream_id
                raise err
            pitch_unit = make_pitch_unit(unit_spec)
            if name == 'stochastic':
                kw['stream_id'] = config.context.rng_id
                kw['seed'] = self.seed
            # chord_progression: i kwarg strutturali NON sono envelope-like e
            # vanno estratti prima della comprehension. In particolare
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
                    structural['duration'] = self.duration
            kw = {k: _parse_strategy_kwarg(val, self.duration, config.time_mode) for k, val in kw.items()}
            kw.update(structural)
            pitch_strategy = VoicePitchStrategyFactory.create(name, **kw)

        # --- ONSET ---
        onset_strategy = None
        if 'onset_offset' in v:
            kw = dict(v['onset_offset'])
            name = kw.pop('strategy')
            if name == 'stochastic':
                kw['stream_id'] = config.context.rng_id
                kw['seed'] = self.seed
            kw = {k: _parse_strategy_kwarg(val, self.duration, config.time_mode) for k, val in kw.items()}
            onset_strategy = VoiceOnsetStrategyFactory.create(name, **kw)

        # --- POINTER ---
        pointer_strategy = None
        if 'pointer' in v:
            kw = dict(v['pointer'])
            name = kw.pop('strategy')
            # Flag di unità: config del blocco, non kwarg di strategy.
            # Solo bool puro: niente coercion silenziosa (cfr. grain.reverse,
            # envelope_builder — il progetto valida i flag, non li forza).
            raw_normalized = kw.pop('normalized', False)
            if not isinstance(raw_normalized, bool):
                err = InvalidFieldValueError(
                    field='voices.pointer.normalized',
                    value=raw_normalized,
                    hint="normalized accetta solo true/false (default: false).",
                )
                err.stream_id = self.stream_id
                raise err
            self._voice_pointer_normalized = raw_normalized
            if name == 'stochastic':
                kw['stream_id'] = config.context.rng_id
                kw['seed'] = self.seed
            kw = {k: _parse_strategy_kwarg(val, self.duration, config.time_mode) for k, val in kw.items()}
            pointer_strategy = VoicePointerStrategyFactory.create(name, **kw)

        # --- PAN ---
        pan_strategy = None
        if 'pan' in v:
            kw = dict(v['pan'])
            name = kw.pop('strategy')
            if name == 'stochastic':
                kw['stream_id'] = config.context.rng_id
                kw['seed'] = self.seed
            kw = {k: _parse_strategy_kwarg(val, self.duration, config.time_mode) for k, val in kw.items()}
            pan_strategy = VoicePanStrategyFactory.create(name, **kw)

        self._voice_manager = VoiceManager(
            max_voices=max_voices,
            pitch_strategy=pitch_strategy,
            onset_strategy=onset_strategy,
            pointer_strategy=pointer_strategy,
            pan_strategy=pan_strategy,
            pitch_unit=pitch_unit,
        )

    def _pre_normalize_grain_params(self, params: dict, output_sr: int) -> dict:
        """
        Conversione di unita' per la durata del grano (modello loop_unit).

        Se grain.duration_unit non e' 'seconds', scala grain.duration e
        grain.duration_range fino ai secondi su scalari ed envelope-like (solo
        i valori Y; l'asse X resta tempo). Il fattore dipende dall'unita':
        1/output_sr per 'samples', 1e-3 per 'milliseconds'.

        Unico punto del sistema che legge 'duration_unit' dal dizionario
        grezzo: e' un meta-parametro che controlla l'interpretazione degli
        altri, non un valore sintetizzabile. Il dict originale non viene
        mutato (cache fingerprint e stream_data_map leggono i dati grezzi).
        """
        grain = params.get('grain')
        if not isinstance(grain, dict) or 'duration_unit' not in grain:
            return params

        unit = grain['duration_unit']
        if unit not in GRAIN_DURATION_UNITS:
            err = InvalidFieldValueError(
                field='grain.duration_unit',
                value=unit,
                hint=f"unità disponibili: {list(GRAIN_DURATION_UNITS)}",
            )
            err.stream_id = self.stream_id
            raise err

        if unit == 'seconds':
            return params

        # Unita' non-secondi: il default seconds (0.05) NON viene scalato. Se
        # grain.duration non e' esplicito, la base resterebbe in secondi mentre
        # duration_range e' nell'unita' dichiarata -> due domini diversi nello
        # stesso blocco. Pretendi una duration esplicita (l'unita' governa base
        # e range insieme).
        label = _GRAIN_DURATION_UNIT_LABELS[unit]
        if grain.get('duration') is None:
            err = MissingFieldError(
                field='grain.duration',
                hint=(f"con grain.duration_unit: {unit} la durata va indicata "
                      f"esplicitamente in {label} (il default 0.05 e' in "
                      "secondi e non verrebbe convertito)."),
            )
            err.stream_id = self.stream_id
            raise err

        # 'samples' dipende dal sample rate di output, 'milliseconds' no.
        factor = (
            1.0 / output_sr if unit == 'samples' else SECONDS_PER_MILLISECOND
        )
        scaled_grain = dict(grain)
        for key in ('duration', 'duration_range'):
            if key in scaled_grain and scaled_grain[key] is not None:
                scaled_grain[key] = scale_raw_param_values(scaled_grain[key], factor)

        scaled_params = dict(params)
        scaled_params['grain'] = scaled_grain
        return scaled_params

    def _init_grain_reverse(self, params: dict) -> None:
        """
        Inizializza parametri reverse del grano.
        
        Semantica YAML RISTRETTA:
        - Chiave ASSENTE → 'auto' (segue pointer_speed)
        - Chiave PRESENTE (reverse:) → DEVE essere vuota, significa True (forzato reverse)
        - reverse: true/false/auto → ERRORE! Non accettati
        
        Examples YAML validi:
            grain:
            # reverse assente → auto mode
            
            grain:
                reverse:  # ← Unico modo per forzare reverse
        
        Examples YAML INVALIDI:
            grain:
                reverse: true    # x ERRORE
                reverse: false   # x ERRORE
                reverse: 'auto'  # x ERRORE
        """
        grain_params = params.get('grain', {})
        
        if 'reverse' in grain_params:
            # Validazione: se la chiave è presente, DEVE essere None (vuota)
            value = grain_params['reverse']
            if value is not None:
                err = InvalidFieldValueError(
                    field='grain.reverse',
                    value=value,
                    hint=(
                        "grain.reverse deve essere lasciato vuoto.\n"
                        "  Sintassi corretta:\n"
                        "    grain:\n"
                        "      reverse:  # senza valore\n"
                        "  Per seguire pointer_speed, ometti completamente 'reverse'."
                    ),
                )
                err.stream_id = self.stream_id
                raise err
            
            # Chiave presente e vuota → reverse forzato
            self.grain_reverse_mode = True
        else:
            # Chiave assente → auto mode (segue speed)
            self.grain_reverse_mode = 'auto'

    # =========================================================================
    # GENERAZIONE GRANI
    # =========================================================================
    
    def generate_grains(self) -> List[List[Grain]]:
        """
        Genera grani per tutte le voci.

        Per ogni tick temporale, genera un grano per ogni voce attiva.
        La densità complessiva è density × num_voices (ogni voce ha il
        proprio loop temporale indipendente con lo stesso inter-onset).

        Returns:
            List[List[Grain]]: grani organizzati per voce (voce 0 = riferimento)
        """
        max_v = self._voice_manager.max_voices

        # Struttura per raccogliere grani per voce (pre-allocata per max_voices)
        all_voice_grains: List[List[Grain]] = [[] for _ in range(max_v)]

        # Cursore temporale indipendente per ogni voce.
        # Con scatter=0 tutti avanzano dello stesso sync_iot → comportamento identico
        # a prima. Con scatter>0 e distribution>0 i cursori divergono nel tempo.
        voice_cursors = [0.0] * max_v

        while any(c < self.duration for c in voice_cursors):
            # Voice 0 è il riferimento: definisce sync_iot e il valore di scatter
            t0 = voice_cursors[0]
            grain_dur_0 = self.grain_duration.get_value(t0)
            sync_iot = self._density.calculate_inter_onset(t0, grain_dur_0)
            scatter_val = self._scatter.get_value(t0)

            for voice_index in range(max_v):
                t = voice_cursors[voice_index]

                if t >= self.duration:
                    continue

                # Voice 0 condivide già grain_dur_0 (t == t0), evita doppia chiamata
                grain_dur = grain_dur_0 if voice_index == 0 else self.grain_duration.get_value(t)

                # num_voices time-varying: la parte frazionaria del valore interpolato
                # diventa un fade di volume sulla voce di confine (quella che si
                # accende/spegne), invece di un on/off netto.
                #   n_full = floor(value)  → voci 0..n_full-1 a volume pieno
                #   frac   = value - n_full → gain della voce di confine (indice n_full)
                # value è già clampato a [1,64] dai bounds; ri-clamp a max_v. Con
                # interpolazione step (breakpoint interi) frac=0 → on/off come prima.
                value = min(float(max_v), self.num_voices.get_value(t))
                n_full = floor(value)
                frac = value - n_full

                if voice_index < n_full:
                    voice_gain = 1.0
                elif voice_index == n_full and frac > 0.0:
                    voice_gain = frac           # voce di confine: fade graduale
                else:
                    voice_gain = 0.0            # voce spenta → nessun grano

                if voice_gain > 0.0:
                    voice_config = self._voice_manager.get_voice_config(voice_index, t)
                    grain = self._create_grain(t, grain_dur, voice_config,
                                               voice_gain=voice_gain)
                    all_voice_grains[voice_index].append(grain)

                # IOT di questa voce: blend tra sync_iot (condiviso) e indep_iot
                if voice_index == 0 or scatter_val == 0.0:
                    iot = sync_iot
                else:
                    indep_iot = self._density.calculate_inter_onset(t, grain_dur)
                    iot = (1.0 - scatter_val) * sync_iot + scatter_val * indep_iot

                voice_cursors[voice_index] += iot

        # Post-process: applica GrainClipStrategy (Plan 001 U2).
        # stream.voices diventa l'unica fonte di verita' su quali grain esistono.
        # Fallback per mock stream creati con object.__new__ senza __init__.
        clip_strategy = getattr(self, '_clip_strategy', None)
        if clip_strategy is None:
            clip_strategy = OverflowMarginClipStrategy(margin=0.0)
        # Assegna ai backing field, non alle property: il getter di .voices
        # innescherebbe ricorsivamente generate_grains (generated ancora False).
        self._voices = clip_strategy.apply(all_voice_grains, self)
        # Flatten e sort per onset (backward compatibility)
        all_grains = [g for voice in self._voices for g in voice]
        all_grains.sort(key=lambda g: g.onset)
        self._grains = all_grains
        self.generated = True

        return self._voices
    
    def _create_grain(self,
                      elapsed_time: float,
                      grain_dur: float,
                      voice_config: Optional['VoiceConfig'] = None,
                      voice_gain: float = 1.0) -> Grain:
        """
        Crea un singolo grano con tutti i parametri calcolati.

        Applica gli offset di VoiceConfig sopra i valori base:
          pitch_ratio  *= pitch_factor   # fattore già materializzato dall'unità
          pointer_pos  = confinato al loop (base + deviazione + pointer_offset)
          pan          += pan_offset
          onset        += onset_offset

        Args:
            elapsed_time: tempo trascorso dall'inizio dello stream
            grain_dur:    durata del grano
            voice_config: offset per questa voce (None = VoiceConfig(1.0,0,0,0))
            voice_gain:   scaler lineare di volume in (0,1] per il fade della voce
                          di confine (1.0 = nessuna attenuazione)

        Returns:
            Grain: oggetto grano completo
        """
        if voice_config is None:
            voice_config = VoiceConfig(1.0, 0.0, 0.0, 0.0)

        grain_reverse = self._calculate_grain_reverse(elapsed_time)

        # === 1. PITCH — base × pitch_factor ===
        # Il fattore di ratio è già materializzato dalla voice pitch strategy
        # tramite la PitchUnit attiva (voce 0 → 1.0). Identità nativa: nessun
        # guard, nessuna conversione qui.
        pitch_ratio = self._pitch.calculate(elapsed_time, grain_reverse=grain_reverse)
        pitch_ratio *= voice_config.pitch_factor

        # === 2. POINTER — base + voice_offset, confinati alla finestra di loop ===
        # Il voice offset viene passato a PointerController.calculate(): con un loop
        # attivo viene confinato DENTRO il loop (wrap modulare), altrimenti sul file
        # intero. calculate() restituisce già la posizione reale di lettura in
        # [0, sample_dur): audio e partitura usano lo stesso valore (issue #79).
        voice_pointer_offset = voice_config.pointer_offset
        if getattr(self, '_voice_pointer_normalized', False):
            voice_pointer_offset *= self.sample_dur_sec
        pointer_pos = self._pointer.calculate(
            elapsed_time, grain_dur, grain_reverse, voice_offset=voice_pointer_offset
        )

        # === 3. VOLUME ===
        volume = self.volume.get_value(elapsed_time)
        # voice_gain in (0,1] dalla parte frazionaria di num_voices: fade della voce
        # di confine. Applicato in dB (riusa il path dB→lineare di NumPy e Csound,
        # nessun nuovo campo su Grain). Clamp al floor del bound volume (-120 dB) per
        # evitare valori assurdi con frac minuscoli. Il chiamante garantisce > 0.
        if voice_gain != 1.0:
            volume = max(-120.0, volume + 20.0 * log10(voice_gain))

        # === 4. PAN — base + voice_offset ===
        pan = self.pan.get_value(elapsed_time) + voice_config.pan_offset

        # === 5. ONSET — assoluto + voice_onset_offset ===
        absolute_onset = self.onset + elapsed_time + voice_config.onset_offset

        # === 6. WINDOW ===
        window_name = self._window_controller.select_window(elapsed_time)
        window_table_num = self.window_table_map[window_name]

        return Grain(
            onset=absolute_onset,
            duration=grain_dur,
            pointer_pos=pointer_pos,
            pitch_ratio=pitch_ratio,
            volume=volume,
            pan=pan,
            sample_table=self.sample_table_num,
            envelope_table=window_table_num
        )


    def _calculate_grain_reverse(self, elapsed_time: float) -> bool:
        """
        Calcola se il grano deve essere riprodotto al contrario.
        
        Usa evaluate_gated_stochastic con variation_mode='invert':
        - 'auto': base_reverse segue pointer_speed
        - grain_reverse_randomness: probabilità di flip (0-100)
        - grain_reverse_randomness=None: nessun flip (mantiene base)
        
        Args:
            elapsed_time: tempo trascorso dall'inizio dello stream
            
        Returns:
            bool: True se grano deve essere riprodotto al contrario
        """
        # 1. Determina base value come float (0.0 o 1.0)
        if self.grain_reverse_mode == 'auto':
            # Se la testina va indietro, il grano è reverse di base
            is_reverse_base = (self._pointer.get_speed(elapsed_time) < 0)
        else:
            # Se forzato da YAML, usiamo il valore caricato nel parametro
            # Nota: self.reverse._value può essere un numero o un Envelope
            val = self.reverse._value
            if hasattr(val, 'evaluate'):
                val = val.evaluate(elapsed_time)
            is_reverse_base = (val > 0.5) if val is not None else True
        
        # FASE 2: Controlliamo se dobbiamo FLIPPARE (DeviationProbability/Probabilità)
        # Usiamo il metodo interno del parametro per vedere se il "dado" vince
        # Nota: Qui stiamo "rubando" la logica probabilistica all'oggetto Parameter
        should_flip = self.reverse._probability_gate.should_apply(elapsed_time)
        
        if should_flip:
            return not is_reverse_base
        return is_reverse_base
    # =========================================================================
    # PROPRIETÀ PER BACKWARD COMPATIBILITY
    # =========================================================================

    @property
    def sampleDurSec(self) -> float:
        """Alias per backward compatibility."""
        return self.sample_dur_sec
        
    @property
    def density(self) -> Optional[Union[float, Envelope]]:
        """Espone density per Generator/ScoreVisualizer."""
        return self._density.density
    
    @property
    def fill_factor(self) -> Optional[Union[float, Envelope]]:
        """Espone fill_factor per Generator/ScoreVisualizer."""
        return self._density.fill_factor
    
    @property
    def distribution(self):
        return self._density.distribution.value if hasattr(self._density.distribution, 'value') else self._density.distribution
        
    @property
    def pointer_speed(self):
        # Il PointerController espone `speed_ratio` (Parameter), non `speed`.
        return self._pointer.speed_ratio.value

    @property
    def loop_start(self):
        """Espone loop_start del PointerController per ScoreVisualizer."""
        return self._pointer.loop_start

    @property
    def loop_end(self):
        """Espone loop_end del PointerController per ScoreVisualizer."""
        return self._pointer.loop_end

    @property
    def loop_dur(self):
        """Espone loop_dur del PointerController per ScoreVisualizer."""
        return self._pointer.loop_dur

    @property
    def pitch_range(self) -> Union[float, Envelope]:
        """Espone pitch_range per ScoreVisualizer."""
        return self._pitch.range

    @property
    def pitch_unit(self):
        """Espone l'unità di pitch attiva (PitchUnit) per ScoreVisualizer."""
        return self._pitch.unit

    @property
    def pitch_value(self):
        """Espone il valore base del pitch (Envelope o scalare) per ScoreVisualizer,
        indipendentemente dall'unità (semitoni/cents/quarti/ottavi/edo/ratio)."""
        return self._pitch.value

    @property
    def num_voices(self):
        """Espone num_voices come Parameter (supporta Envelope time-varying)."""
        return self._num_voices

    @property
    def pointer_deviation(self):
        """Parameter della deviazione per-grano del pointer.

        Vive dentro PointerController: senza questo accessore chi legge le
        curve dello stream deve arrivarci per via privata
        (stream._pointer.deviation).
        """
        return getattr(self._pointer, 'deviation', None)

    @property
    def effective_density_curve(self):
        """La densita' reale della voce 0 in grani/secondo, come curva.

        `fill_factor` da solo non dice quanti grani al secondo si ascoltano:
        la densita' vera e' `fill_factor(t) / grain_duration(t)`, che il
        motore calcola a ogni onset (`generate_grains` -> voce 0 ->
        `calculate_inter_onset`) e non conserva. Qui viene campionata.

        Voce 0, la voce di riferimento: e' lei a definire il `sync_iot`. Con
        piu' voci i grani totali sono di piu' — `num_voices` e' una riga a
        parte della partitura.

        None in modalita' `density`: li' sarebbe la copia esatta del
        parametro `density`, gia' disegnato sotto il suo nome.
        """
        return self._density.density_curve(
            self.duration,
            grain_duration_at=lambda t: nominal_value(self.grain_duration, t),
        )

    @property
    def voice_manager(self):
        """VoiceManager dello stream: sa campionare le curve degli offset
        per-voce (VoiceManager.offset_curves)."""
        return self._voice_manager

    @property
    def scatter(self):
        """Espone scatter come Parameter (supporta Envelope time-varying)."""
        return self._scatter

    # =========================================================================
    # GRANI LAZY (issue #117)
    # =========================================================================

    @property
    def voices(self) -> List[List[Grain]]:
        """Grani organizzati per voce. Lazy: genera al primo accesso."""
        if not self.generated:
            self.generate_grains()
        return self._voices

    @voices.setter
    def voices(self, value: List[List[Grain]]) -> None:
        """Iniezione esplicita dei grani (test/consumer): materializza lo stato.

        Assegnare voices significa "i grani sono questi": marca generated=True
        cosi' una lettura successiva non rigenera sovrascrivendo il valore.
        """
        self._voices = value
        self.generated = True

    @property
    def grains(self) -> List[Grain]:
        """Vista flat dei grani (backward compat). Lazy: genera al primo accesso."""
        if not self.generated:
            self.generate_grains()
        return self._grains

    @grains.setter
    def grains(self, value: List[Grain]) -> None:
        self._grains = value
        self.generated = True

    # =========================================================================
    # REPR
    # =========================================================================

    def __repr__(self) -> str:
        mode = "fill_factor" if self.fill_factor is not None else "density"
        # NON innescare la generazione lazy: _create_streams stampa {stream} per
        # ogni stream; leggere la property .grains rigenererebbe tutto.
        grain_count = len(self._grains) if self.generated else 'lazy'
        return (f"Stream(id={self.stream_id}, onset={self.onset}, "
                f"dur={self.duration}, mode={mode}, grains={grain_count})")
