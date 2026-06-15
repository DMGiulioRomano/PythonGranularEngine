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
from typing import List, Optional, Union

from core.grain import Grain
from envelopes.envelope import Envelope, create_scaled_envelope
from controllers.window_controller import WindowController
from controllers.pointer_controller import PointerController
from controllers.pitch_controller import PitchController
from controllers.density_controller import DensityController
from shared.utils import get_sample_duration
from shared.exceptions import (
    InvalidFieldValueError,
    InvalidStrategyConfigError,
    MissingFieldError,
    SampleNotFoundError,
)
from parameters.parameter_schema import STREAM_PARAMETER_SCHEMA
from parameters.parameter_orchestrator import ParameterOrchestrator
from core.stream_config import StreamConfig, StreamContext
from controllers.voice_manager import VoiceManager, VoiceConfig
from parameters.pitch_unit import make_pitch_unit
from strategies.voice_pitch_strategy import VoicePitchStrategyFactory, SEMITONE_LOCKED
from strategies.voice_onset_strategy import VoiceOnsetStrategyFactory
from strategies.voice_pointer_strategy import VoicePointerStrategyFactory
from strategies.voice_pan_strategy import VoicePanStrategyFactory
from strategies.grain_clip_strategy import GrainClipStrategyFactory, OverflowMarginClipStrategy
from dataclasses import fields


def _parse_strategy_kwarg(value, duration: float):
    """Converte kwarg YAML strategy: str/int passthrough, envelope-like → Envelope."""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return value
    if Envelope.is_envelope_like(value):
        if isinstance(value, dict) and value.get('time_mode') == 'normalized':
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
    
    def __init__(self, params: dict, seed=None):
        """
        Inizializza lo stream dai parametri YAML.

        Args:
            params: dizionario parametri dallo YAML
            seed: seed YAML top-level (issue #81), propagato alle voice strategy
                  stocastiche per la riproducibilità fra processi. None (default)
                  → comportamento legacy (hash() per-voce).
        """
        # Seed di riproducibilità: iniettato nelle strategy stocastiche in
        # _init_voice_manager. None → fallback hash() (retrocompat).
        self.seed = seed
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
            sample_dur = get_sample_duration(sample)
        except SampleNotFoundError as err:
            err.stream_id = stream_id
            raise
        self._check_required_context_fields(params, stream_id)
        config = StreamConfig.from_yaml(params, StreamContext.from_yaml(params, sample_dur_sec=sample_dur))
        self._init_stream_context(params)
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

    def _check_required_context_fields(self, params, stream_id):
        """Verifica campi obbligatori StreamContext prima di StreamConfig.from_yaml."""
        base = {field.name for field in fields(StreamContext) if field.name != 'sample_dur_sec'}
        missing = base - set(params.keys())
        if missing:
            missing_list = sorted(missing)
            err = MissingFieldError(fields=missing_list)
            err.stream_id = stream_id
            raise err

    def _init_stream_context(self, params):
        self._check_required_context_fields(params, params.get('stream_id', 'unknown'))
        base = {field.name for field in fields(StreamContext) if field.name != 'sample_dur_sec'}
        for key in base:
            setattr(self, key, params[key])
        self.sample_dur_sec = get_sample_duration(self.sample)

    def _init_stream_parameters(self, params: dict, config: StreamConfig) -> None:
        """
        Inizializza parametri diretti di Stream usando ParameterFactory.
        
        Design Pattern: Data-Driven Configuration
        - Lo schema STREAM_PARAMETER_SCHEMA definisce COSA caricare
        - ParameterFactory sa COME crearlo
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
        - strategy stochastiche: stream_id iniettato automaticamente
        - spread estratto dal blocco pan
        """
        from parameters.parameter import Parameter
        from parameters.parameter_definitions import GRANULAR_PARAMETERS

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

        from parameters.parser import GranularParser
        parser = GranularParser(config)

        raw_num_voices = v.get('num_voices', 1)

        # Parsa num_voices come Parameter (supporta Envelope time-varying, incluso formato dict).
        self._num_voices = parser.parse_parameter('num_voices', raw_num_voices)

        # Estrae max_voices per pre-computare tutti i VoiceConfig all'init.
        # Se num_voices è un Envelope, max_voices = picco dei breakpoints.
        param_val = self._num_voices.value
        if isinstance(param_val, Envelope):
            max_voices = int(max(bp[1] for bp in param_val.breakpoints))
        else:
            max_voices = int(param_val)
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
                kw['stream_id'] = self.stream_id
                kw['seed'] = self.seed
            kw = {k: _parse_strategy_kwarg(val, self.duration) for k, val in kw.items()}
            pitch_strategy = VoicePitchStrategyFactory.create(name, **kw)

        # --- ONSET ---
        onset_strategy = None
        if 'onset_offset' in v:
            kw = dict(v['onset_offset'])
            name = kw.pop('strategy')
            if name == 'stochastic':
                kw['stream_id'] = self.stream_id
                kw['seed'] = self.seed
            kw = {k: _parse_strategy_kwarg(val, self.duration) for k, val in kw.items()}
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
                kw['stream_id'] = self.stream_id
                kw['seed'] = self.seed
            kw = {k: _parse_strategy_kwarg(val, self.duration) for k, val in kw.items()}
            pointer_strategy = VoicePointerStrategyFactory.create(name, **kw)

        # --- PAN ---
        pan_strategy = None
        pan_spread = 0.0
        if 'pan' in v:
            kw = dict(v['pan'])
            name = kw.pop('strategy')
            pan_spread = _parse_strategy_kwarg(kw.pop('spread', 0.0), self.duration)
            if name == 'random':
                kw['stream_id'] = self.stream_id
                kw['seed'] = self.seed
            pan_strategy = VoicePanStrategyFactory.create(name, **kw)

        self._voice_manager = VoiceManager(
            max_voices=max_voices,
            pitch_strategy=pitch_strategy,
            onset_strategy=onset_strategy,
            pointer_strategy=pointer_strategy,
            pan_strategy=pan_strategy,
            pan_spread=pan_spread,
            pitch_unit=pitch_unit,
        )

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
                active = max(1, min(max_v, int(self.num_voices.get_value(t))))

                if voice_index < active:
                    voice_config = self._voice_manager.get_voice_config(voice_index, t)
                    grain = self._create_grain(t, grain_dur, voice_config)
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
                      voice_config: Optional['VoiceConfig'] = None) -> Grain:
        """
        Crea un singolo grano con tutti i parametri calcolati.

        Applica gli offset di VoiceConfig sopra i valori base:
          pitch_ratio  *= pitch_factor   # fattore già materializzato dall'unità
          pointer_pos  = (base + pointer_offset) % sample_dur_sec
          pan          += pan_offset
          onset        += onset_offset

        Args:
            elapsed_time: tempo trascorso dall'inizio dello stream
            grain_dur:    durata del grano
            voice_config: offset per questa voce (None = VoiceConfig(1.0,0,0,0))

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

        # === 2. POINTER — base + voice_offset, re-wrap in [0, sample_dur) ===
        # Il modulo mappa anche offset negativi in [0, sample_dur). Così
        # grain.pointer_pos è la posizione reale di lettura: audio e partitura
        # usano lo stesso valore (issue #79).
        pointer_pos = self._pointer.calculate(elapsed_time, grain_dur, grain_reverse)
        voice_pointer_offset = voice_config.pointer_offset
        if getattr(self, '_voice_pointer_normalized', False):
            voice_pointer_offset *= self.sample_dur_sec
        pointer_pos = (pointer_pos + voice_pointer_offset) % self.sample_dur_sec

        # === 3. VOLUME ===
        volume = self.volume.get_value(elapsed_time)

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
        
        # FASE 2: Controlliamo se dobbiamo FLIPPARE (Dephase/Probabilità)
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
